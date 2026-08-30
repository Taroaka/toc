from __future__ import annotations

from copy import deepcopy
import asyncio
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch as mock_patch

import yaml

from server import image_gen_app
from toc.semantic_repair_patch import (
    SemanticRepairPatchError,
    apply_semantic_repair_patch_documents,
)
from toc.run_root_binding import bind_run_root
from toc.semantic_review import (
    LEGACY_SEMANTIC_REVIEW_INPUT_SCHEMA,
    SEMANTIC_REVIEW_INPUT_SCHEMA,
    semantic_review_input_digest,
    semantic_review_scope_binding_sha256,
)


def _scene(scene_id: int) -> dict:
    beat_id = f"scene{scene_id:02d}_event_turn"
    return {
        "scene_id": scene_id,
        "scene_intent": {
            "handoff_chain": {
                "incoming": {
                    "visible_or_audible_form": "古い引き継ぎ",
                }
            },
            "story_event_obligations": [
                {
                    "event_id": beat_id,
                    "source_event_beat_id": beat_id,
                    "source_events": ["古い出来事"],
                }
            ],
        },
        "scene_event": {
            "event_sequence": [
                {
                    "beat_id": beat_id,
                    "beat_function": "turn",
                    "what_happens": "古い出来事",
                    "visible_action": "古い行動",
                    "visible_reaction": "古い反応",
                    "required_visual_evidence": ["古い証拠"],
                    "concrete_event": {
                        "what_happens": "古い出来事",
                        "visible_action": "古い行動",
                        "visible_reaction": "古い反応",
                        "required_visual_evidence": ["古い証拠"],
                    },
                    "story_grounding": {
                        "source_origin": "canonical_reference",
                        "source_story_beat_ids": ["source_event_01"],
                        "source_text_or_summary": "原典の出来事",
                        "non_replaceable_elements": [
                            {
                                "element_id": "hero",
                                "type": "character",
                                "value": "主人公",
                                "why_non_replaceable": "主人公だから",
                            }
                        ],
                    },
                }
            ],
            "forbidden_event_changes": [],
        },
        "cuts": [],
    }


def _documents() -> tuple[dict, dict, dict]:
    script = {"scenes": [_scene(10), _scene(20)]}
    manifest = deepcopy(script)
    return script, manifest, {"assets": []}


def _patch(*operations: dict) -> dict:
    return {
        "schema_version": "semantic_repair_patch_v1",
        "stage": "scene_set",
        "semantic_review_input_digest": "sha256:" + "a" * 64,
        "operations": list(operations),
    }


class SemanticRepairPatchTests(unittest.TestCase):
    def test_patch_only_producer_writes_no_source_files_and_orchestrator_applies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run"
            run_dir.mkdir()
            script, manifest, _asset_plan = _documents()
            for name, data in (("script.md", script), ("video_manifest.md", manifest)):
                (run_dir / name).write_text(
                    f"# {name}\n\n```yaml\n"
                    + yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
                    + "```\n",
                    encoding="utf-8",
                )
            image_gen_app.append_state_snapshot(run_dir / "state.txt", {})
            relpaths = image_gen_app.semantic_review_relpaths("scene_set")
            collection = run_dir / relpaths["collection"]
            scope_path = run_dir / relpaths["scope"]
            prompt_path = run_dir / relpaths["prompt"]
            report_path = run_dir / relpaths["report"]
            collection.parent.mkdir(parents=True, exist_ok=True)
            collection.write_text(
                "# collection\n\n## scene:20\nfailed scene\n",
                encoding="utf-8",
            )
            prompt_path.write_text("# review prompt\n", encoding="utf-8")
            source_digests = [
                {
                    "path": name,
                    "sha256": hashlib.sha256((run_dir / name).read_bytes()).hexdigest(),
                }
                for name in ("script.md", "video_manifest.md")
            ]
            scope = {
                "stage": "scene_set",
                "entry_count": 1,
                "entry_ids": ["scene:20"],
                "review_scope": "all_entries",
                "source_artifacts": ["script.md", "video_manifest.md"],
                "semantic_review_input_schema": SEMANTIC_REVIEW_INPUT_SCHEMA,
                "source_artifact_digests": source_digests,
                "collection_sha256": hashlib.sha256(collection.read_bytes()).hexdigest(),
                "prompt_sha256": hashlib.sha256(prompt_path.read_bytes()).hexdigest(),
                "artifacts": {key: value.as_posix() for key, value in relpaths.items()},
            }
            scope_binding = semantic_review_scope_binding_sha256(scope)
            scope["scope_binding_sha256"] = scope_binding
            scope["semantic_review_input_digest"] = semantic_review_input_digest(
                stage="scene_set",
                entry_ids=["scene:20"],
                collection_sha256=scope["collection_sha256"],
                prompt_sha256=scope["prompt_sha256"],
                source_artifact_digests=source_digests,
                scope_binding_sha256=scope_binding,
            )
            scope_path.write_text(json.dumps(scope) + "\n", encoding="utf-8")
            report_path.write_text(
                "status: failed\n"
                f"semantic_review_input_digest: {scope['semantic_review_input_digest']}\n"
                "reviewed_entries: [scene:20]\n"
                "blocked_entries: [scene:20]\n"
                "findings: [handoff mismatch]\n"
                "failed_selectors: [scene:20]\n"
                "reason_keys: [scene_set.handoff_state_mismatch]\n"
                "notes: []\n",
                encoding="utf-8",
            )
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)

            class FakeClient:
                def __init__(self) -> None:
                    self.calls = 0

                async def start_thread(self, **_kwargs):
                    return "thread-1"

                async def run_turn(self, *, cwd: Path, **_kwargs):
                    self.calls += 1
                    patch_path = Path(cwd) / image_gen_app.semantic_repair_relpaths(
                        "scene_set", 1
                    )["patch"]
                    payload = json.loads(patch_path.read_text(encoding="utf-8"))
                    payload["operations"] = (
                        [
                            {
                                "op": "replace",
                                "artifact": "script.md",
                                "selector": "scene:20",
                                "path": "scene_id",
                                "expected_old": 20,
                                "value": 999,
                                "reason_key": "semantic_timeline_mismatch",
                            }
                        ]
                        if self.calls == 1
                        else [
                            {
                                "op": "replace",
                                "artifact": "script.md",
                                "selector": "scene:20",
                                "path": "scene_intent.handoff_chain.incoming.visible_or_audible_form",
                                "expected_old": "古い引き継ぎ",
                                "value": "scene10の終端状態を受ける",
                                "reason_key": "scene_set.handoff_state_mismatch",
                            }
                        ]
                    )
                    patch_path.write_text(
                        json.dumps(payload, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    return []

                async def stop(self):
                    return None

            with bind_run_root(run_dir, expected_identity=identity) as binding:
                paths = image_gen_app.write_semantic_repair_prompt(
                    run_dir,
                    "scene_set",
                    round_number=1,
                    max_attempts=2,
                    errors=["handoff mismatch"],
                    expected_root_identity=identity,
                )
                fake_client = FakeClient()
                with mock_patch(
                    "server.image_gen_app.create_codex_app_server_client",
                    return_value=fake_client,
                ):
                    changed = asyncio.run(
                        image_gen_app._run_semantic_patch_producer_repair(
                            job_id="job-1",
                            run_dir=run_dir,
                            binding=binding,
                            stage="scene_set",
                            round_number=1,
                            errors=("handoff mismatch",),
                            target_selectors=["scene:20"],
                            paths=paths,
                        )
                    )

            self.assertEqual(changed, ["script.md", "video_manifest.md"])
            self.assertEqual(fake_client.calls, 2)
            _text, updated = image_gen_app.load_structured_document(
                run_dir / "script.md"
            )
            self.assertEqual(
                updated["scenes"][1]["scene_intent"]["handoff_chain"]
                ["incoming"]["visible_or_audible_form"],
                "scene10の終端状態を受ける",
            )
            report = (
                run_dir
                / image_gen_app.semantic_repair_relpaths("scene_set", 1)[
                    "report"
                ]
            ).read_text(encoding="utf-8")
            self.assertIn(
                "generated_by: deterministic_semantic_patch_orchestrator",
                report,
            )

    def test_applies_existing_allowed_key_and_projects_manifest(self) -> None:
        script, manifest, asset_plan = _documents()
        patch = _patch(
            {
                "op": "replace",
                "artifact": "script.md",
                "selector": "scene:20",
                "path": (
                    "scene_intent.handoff_chain.incoming."
                    "visible_or_audible_form"
                ),
                "expected_old": "古い引き継ぎ",
                "value": "scene10の終端状態を受ける",
                "reason_key": "scene_set.handoff_state_mismatch",
            }
        )

        result = apply_semantic_repair_patch_documents(
            stage="scene_set",
            expected_review_input_digest="sha256:" + "a" * 64,
            patch=patch,
            script=script,
            manifest=manifest,
            asset_plan=asset_plan,
            allowed_selectors=["scene:20"],
        )

        self.assertEqual(result.applied_operation_count, 1)
        for document in (script, manifest):
            self.assertEqual(
                document["scenes"][1]["scene_intent"]["handoff_chain"]
                ["incoming"]["visible_or_audible_form"],
                "scene10の終端状態を受ける",
            )

    def test_allows_projector_owned_manifest_metadata_changes(self) -> None:
        script, manifest, asset_plan = _documents()
        manifest["schema_version"] = "stale_provider_projection"
        patch = _patch(
            {
                "op": "replace",
                "artifact": "script.md",
                "selector": "scene:20",
                "path": "scene_intent.handoff_chain.incoming.visible_or_audible_form",
                "expected_old": "古い引き継ぎ",
                "value": "scene10の終端状態を受ける",
                "reason_key": "scene_set.handoff_state_mismatch",
            }
        )

        def project(*, script, manifest, asset_plan):
            manifest["schema_version"] = "deterministically_projected"
            return object()

        with mock_patch(
            "toc.semantic_repair_patch.reconcile_semantic_repair_documents",
            side_effect=project,
        ):
            result = apply_semantic_repair_patch_documents(
                stage="scene_set",
                expected_review_input_digest="sha256:" + "a" * 64,
                patch=patch,
                script=script,
                manifest=manifest,
                asset_plan=asset_plan,
                allowed_selectors=["scene:20"],
            )

        self.assertEqual(result.applied_operation_count, 1)
        self.assertEqual(
            manifest["schema_version"],
            "deterministically_projected",
        )

    def test_rejects_protected_identity_and_source_ownership_keys(self) -> None:
        for path, value in (
            ("scene_id", 999),
            (
                "scene_event.event_sequence[beat_id=scene20_event_turn].beat_id",
                "forged_beat",
            ),
            (
                "scene_event.event_sequence[beat_id=scene20_event_turn]."
                "story_grounding.source_story_beat_ids",
                ["forged_source"],
            ),
        ):
            with self.subTest(path=path):
                script, manifest, asset_plan = _documents()
                with self.assertRaisesRegex(
                    SemanticRepairPatchError,
                    "protected_path",
                ):
                    apply_semantic_repair_patch_documents(
                        stage="scene_set",
                        expected_review_input_digest="sha256:" + "a" * 64,
                        patch=_patch(
                            {
                                "op": "replace",
                                "artifact": "script.md",
                                "selector": "scene:20",
                                "path": path,
                                "expected_old": None,
                                "value": value,
                                "reason_key": "semantic_timeline_mismatch",
                            }
                        ),
                        script=script,
                        manifest=manifest,
                        asset_plan=asset_plan,
                        allowed_selectors=["scene:20"],
                    )

    def test_rejects_wrong_stage_artifact_selector_and_wildcard_path(self) -> None:
        cases = (
            ({"artifact": "video_manifest.md"}, "artifact_not_allowed"),
            ({"selector": "scene:999"}, "selector_not_found"),
            (
                {
                    "path": (
                        "scene_event.event_sequence[*].visible_action"
                    )
                },
                "path_not_exact",
            ),
            ({"path": "review.semantic.status"}, "protected_path"),
        )
        base = {
            "op": "replace",
            "artifact": "script.md",
            "selector": "scene:20",
            "path": "scene_intent.handoff_chain.incoming.visible_or_audible_form",
            "expected_old": "古い引き継ぎ",
            "value": "新しい引き継ぎ",
            "reason_key": "scene_set.handoff_state_mismatch",
        }
        for override, code in cases:
            with self.subTest(code=code):
                script, manifest, asset_plan = _documents()
                operation = {**base, **override}
                with self.assertRaisesRegex(SemanticRepairPatchError, code):
                    apply_semantic_repair_patch_documents(
                        stage="scene_set",
                        expected_review_input_digest="sha256:" + "a" * 64,
                        patch=_patch(operation),
                        script=script,
                        manifest=manifest,
                        asset_plan=asset_plan,
                        allowed_selectors=["scene:20"],
                    )

    def test_rejects_selector_outside_current_failure_scope(self) -> None:
        script, manifest, asset_plan = _documents()
        with self.assertRaisesRegex(
            SemanticRepairPatchError,
            "selector_outside_failure_scope",
        ):
            apply_semantic_repair_patch_documents(
                stage="scene_set",
                expected_review_input_digest="sha256:" + "a" * 64,
                patch=_patch(
                    {
                        "op": "replace",
                        "artifact": "script.md",
                        "selector": "scene:20",
                        "path": "scene_intent.handoff_chain.incoming.visible_or_audible_form",
                        "expected_old": "古い引き継ぎ",
                        "value": "新しい引き継ぎ",
                        "reason_key": "scene_set.handoff_state_mismatch",
                    }
                ),
                script=script,
                manifest=manifest,
                asset_plan=asset_plan,
                allowed_selectors=["scene:10"],
            )

    def test_rejects_stale_expected_old_without_mutating_documents(self) -> None:
        script, manifest, asset_plan = _documents()
        before = deepcopy((script, manifest, asset_plan))
        with self.assertRaisesRegex(
            SemanticRepairPatchError,
            "expected_old_mismatch",
        ):
            apply_semantic_repair_patch_documents(
                stage="scene_set",
                expected_review_input_digest="sha256:" + "a" * 64,
                patch=_patch(
                    {
                        "op": "replace",
                        "artifact": "script.md",
                        "selector": "scene:20",
                        "path": "scene_intent.handoff_chain.incoming.visible_or_audible_form",
                        "expected_old": "存在しない旧値",
                        "value": "新値",
                        "reason_key": "scene_set.handoff_state_mismatch",
                    }
                ),
                script=script,
                manifest=manifest,
                asset_plan=asset_plan,
                allowed_selectors=["scene:20"],
            )
        self.assertEqual((script, manifest, asset_plan), before)

    def test_multiple_operations_are_atomic_when_one_is_invalid(self) -> None:
        script, manifest, asset_plan = _documents()
        before = deepcopy((script, manifest, asset_plan))
        with self.assertRaisesRegex(
            SemanticRepairPatchError,
            "expected_old_mismatch",
        ):
            apply_semantic_repair_patch_documents(
                stage="scene_set",
                expected_review_input_digest="sha256:" + "a" * 64,
                patch=_patch(
                    {
                        "op": "replace",
                        "artifact": "script.md",
                        "selector": "scene:20",
                        "path": "scene_event.event_sequence[beat_id=scene20_event_turn].visible_action",
                        "expected_old": "古い行動",
                        "value": "主人公が扉を閉じる",
                        "reason_key": "scene_set.causal_proof_weak",
                    },
                    {
                        "op": "replace",
                        "artifact": "script.md",
                        "selector": "scene:20",
                        "path": "scene_event.event_sequence[beat_id=scene20_event_turn].visible_reaction",
                        "expected_old": "誤った旧値",
                        "value": "家族が振り返る",
                        "reason_key": "semantic_subject_mismatch",
                    },
                ),
                script=script,
                manifest=manifest,
                asset_plan=asset_plan,
                allowed_selectors=["scene:20"],
            )
        self.assertEqual((script, manifest, asset_plan), before)

    def test_rejects_duplicate_path_and_provider_facing_cut_field(self) -> None:
        script, manifest, asset_plan = _documents()
        duplicate = {
            "op": "replace",
            "artifact": "script.md",
            "selector": "scene:20",
            "path": "scene_intent.handoff_chain.incoming.visible_or_audible_form",
            "expected_old": "古い引き継ぎ",
            "value": "新しい引き継ぎ",
            "reason_key": "scene_set.handoff_state_mismatch",
        }
        with self.assertRaisesRegex(
            SemanticRepairPatchError,
            "duplicate_operation_path",
        ):
            apply_semantic_repair_patch_documents(
                stage="scene_set",
                expected_review_input_digest="sha256:" + "a" * 64,
                patch=_patch(duplicate, duplicate),
                script=script,
                manifest=manifest,
                asset_plan=asset_plan,
                allowed_selectors=["scene:20"],
            )

    def test_rejects_digest_stage_and_shape_mismatch(self) -> None:
        script, manifest, asset_plan = _documents()
        for override, code in (
            ({"stage": "scene_detail"}, "stage_mismatch"),
            (
                {"semantic_review_input_digest": "sha256:" + "b" * 64},
                "review_digest_mismatch",
            ),
            ({"operations": []}, "operations_empty"),
        ):
            with self.subTest(code=code):
                payload = {**_patch(), **override}
                with self.assertRaisesRegex(SemanticRepairPatchError, code):
                    apply_semantic_repair_patch_documents(
                        stage="scene_set",
                        expected_review_input_digest="sha256:" + "a" * 64,
                        patch=payload,
                        script=script,
                        manifest=manifest,
                        asset_plan=asset_plan,
                        allowed_selectors=["scene:20"],
                    )

    def test_requires_nonempty_failure_scope(self) -> None:
        script, manifest, asset_plan = _documents()
        with self.assertRaisesRegex(
            SemanticRepairPatchError,
            "selector_scope_missing",
        ):
            apply_semantic_repair_patch_documents(
                stage="scene_set",
                expected_review_input_digest="sha256:" + "a" * 64,
                patch=_patch(
                    {
                        "op": "replace",
                        "artifact": "script.md",
                        "selector": "scene:20",
                        "path": "scene_intent.handoff_chain.incoming.visible_or_audible_form",
                        "expected_old": "古い引き継ぎ",
                        "value": "新しい引き継ぎ",
                        "reason_key": "scene_set.handoff_state_mismatch",
                    }
                ),
                script=script,
                manifest=manifest,
                asset_plan=asset_plan,
            )

    def test_cut_failure_scope_does_not_authorize_parent_or_sibling(self) -> None:
        base_cut = {
            "cut_id": "01",
            "selector": "scene20_cut01",
            "visual_beat": "古いcut01",
        }
        sibling_cut = {
            "cut_id": "02",
            "selector": "scene20_cut02",
            "visual_beat": "古いcut02",
        }
        for selector, path, old, code in (
            (
                "scene:20",
                "scene_event.event_sequence[beat_id=scene20_event_turn].visible_action",
                "古い行動",
                "selector_outside_failure_scope",
            ),
            (
                "scene20_cut02",
                "visual_beat",
                "古いcut02",
                "selector_outside_failure_scope",
            ),
        ):
            with self.subTest(selector=selector):
                script, manifest, asset_plan = _documents()
                script["scenes"][1]["cuts"] = [deepcopy(base_cut), deepcopy(sibling_cut)]
                manifest["scenes"][1]["cuts"] = [deepcopy(base_cut), deepcopy(sibling_cut)]
                payload = {
                    **_patch(
                        {
                            "op": "replace",
                            "artifact": "script.md",
                            "selector": selector,
                            "path": path,
                            "expected_old": old,
                            "value": "修正値",
                            "reason_key": "cut_blueprint.semantic_mismatch",
                        }
                    ),
                    "stage": "scene_detail",
                }
                with self.assertRaisesRegex(SemanticRepairPatchError, code):
                    apply_semantic_repair_patch_documents(
                        stage="scene_detail",
                        expected_review_input_digest="sha256:" + "a" * 64,
                        patch=payload,
                        script=script,
                        manifest=manifest,
                        asset_plan=asset_plan,
                        allowed_selectors=["scene20_cut01"],
                    )

        script, manifest, asset_plan = _documents()
        script["scenes"][1]["cuts"] = [deepcopy(base_cut), deepcopy(sibling_cut)]
        manifest["scenes"][1]["cuts"] = [deepcopy(base_cut), deepcopy(sibling_cut)]
        result = apply_semantic_repair_patch_documents(
            stage="scene_detail",
            expected_review_input_digest="sha256:" + "a" * 64,
            patch={
                **_patch(
                    {
                        "op": "replace",
                        "artifact": "script.md",
                        "selector": "scene20_cut01",
                        "path": "visual_beat",
                        "expected_old": "古いcut01",
                        "value": "修正済みcut01",
                        "reason_key": "cut_blueprint.semantic_mismatch",
                    }
                ),
                "stage": "scene_detail",
            },
            script=script,
            manifest=manifest,
            asset_plan=asset_plan,
            allowed_selectors=["scene20_cut01"],
        )
        self.assertEqual(result.changed_selectors, ("scene20_cut01",))

    def test_scene_failure_scope_may_authorize_child_cut(self) -> None:
        cut = {
            "cut_id": "01",
            "selector": "scene20_cut01",
            "visual_beat": "古いcut",
        }
        script, manifest, asset_plan = _documents()
        script["scenes"][1]["cuts"] = [deepcopy(cut)]
        manifest["scenes"][1]["cuts"] = [deepcopy(cut)]
        result = apply_semantic_repair_patch_documents(
            stage="scene_detail",
            expected_review_input_digest="sha256:" + "a" * 64,
            patch={
                **_patch(
                    {
                        "op": "replace",
                        "artifact": "script.md",
                        "selector": "scene20_cut01",
                        "path": "visual_beat",
                        "expected_old": "古いcut",
                        "value": "新しいcut",
                        "reason_key": "scene_detail.semantic_mismatch",
                    }
                ),
                "stage": "scene_detail",
            },
            script=script,
            manifest=manifest,
            asset_plan=asset_plan,
            allowed_selectors=["scene:20"],
        )
        self.assertEqual(result.changed_selectors, ("scene20_cut01",))

    def test_dotted_cut_scope_does_not_collapse_to_integer_cut(self) -> None:
        dotted_scene = _scene(31)
        dotted_scene["scene_id"] = "3.1"
        dotted_scene["scene_event"]["event_sequence"][0]["beat_id"] = (
            "scene3.1_event_turn"
        )
        dotted_obligation = dotted_scene["scene_intent"][
            "story_event_obligations"
        ][0]
        dotted_obligation["event_id"] = "scene3.1_event_turn"
        dotted_obligation["source_event_beat_id"] = "scene3.1_event_turn"
        cut_two = {
            "cut_id": "2",
            "selector": "scene3.1_cut2",
            "visual_beat": "integer cut",
        }
        cut_two_one = {
            "cut_id": "2.1",
            "selector": "scene3.1_cut2.1",
            "visual_beat": "dotted cut",
        }
        for attempted_selector in ("scene3.1_cut2",):
            script = {"scenes": [deepcopy(dotted_scene)]}
            script["scenes"][0]["cuts"] = [deepcopy(cut_two), deepcopy(cut_two_one)]
            manifest = deepcopy(script)
            before = deepcopy((script, manifest))
            with self.assertRaisesRegex(
                SemanticRepairPatchError,
                "selector_outside_failure_scope",
            ):
                apply_semantic_repair_patch_documents(
                    stage="scene_detail",
                    expected_review_input_digest="sha256:" + "a" * 64,
                    patch={
                        **_patch(
                            {
                                "op": "replace",
                                "artifact": "script.md",
                                "selector": attempted_selector,
                                "path": "visual_beat",
                                "expected_old": "integer cut",
                                "value": "wrongly changed",
                                "reason_key": "scene_detail.semantic_mismatch",
                            }
                        ),
                        "stage": "scene_detail",
                    },
                    script=script,
                    manifest=manifest,
                    asset_plan={"assets": []},
                    allowed_selectors=["scene3.1_cut2.1"],
                )
            self.assertEqual((script, manifest), before)

        script = {"scenes": [deepcopy(dotted_scene)]}
        script["scenes"][0]["cuts"] = [deepcopy(cut_two), deepcopy(cut_two_one)]
        manifest = deepcopy(script)
        result = apply_semantic_repair_patch_documents(
            stage="scene_detail",
            expected_review_input_digest="sha256:" + "a" * 64,
            patch={
                **_patch(
                    {
                        "op": "replace",
                        "artifact": "script.md",
                        "selector": "scene3.1_cut2.1",
                        "path": "visual_beat",
                        "expected_old": "dotted cut",
                        "value": "dotted cut repaired",
                        "reason_key": "scene_detail.semantic_mismatch",
                    }
                ),
                "stage": "scene_detail",
            },
            script=script,
            manifest=manifest,
            asset_plan={"assets": []},
            allowed_selectors=["scene3.1_cut2.1"],
        )
        self.assertEqual(result.changed_selectors, ("scene3.1_cut2.1",))

    def test_rejects_reveal_source_and_evidence_ids_and_parent_containers(self) -> None:
        for path, expected_old, value in (
            (
                "scene_event.story_information_revealed_ids",
                ["info_01"],
                ["forged_info"],
            ),
            (
                "scene_event.source_ref_ids",
                ["source_ref_01"],
                ["forged_source"],
            ),
            (
                "scene_event.required_evidence_ids",
                ["evidence_01"],
                ["forged_evidence"],
            ),
            (
                "scene_event.event_sequence[beat_id=scene20_event_turn].story_grounding",
                None,
                {"source_story_beat_ids": ["forged_source"]},
            ),
        ):
            with self.subTest(path=path):
                script, manifest, asset_plan = _documents()
                scene_event = script["scenes"][1]["scene_event"]
                manifest_event = manifest["scenes"][1]["scene_event"]
                if path.startswith("scene_event.story_information"):
                    scene_event["story_information_revealed_ids"] = ["info_01"]
                    manifest_event["story_information_revealed_ids"] = ["info_01"]
                elif path.startswith("scene_event.source_ref_ids"):
                    scene_event["source_ref_ids"] = ["source_ref_01"]
                    manifest_event["source_ref_ids"] = ["source_ref_01"]
                elif path.startswith("scene_event.required_evidence_ids"):
                    scene_event["required_evidence_ids"] = ["evidence_01"]
                    manifest_event["required_evidence_ids"] = ["evidence_01"]
                else:
                    expected_old = deepcopy(
                        scene_event["event_sequence"][0]["story_grounding"]
                    )
                with self.assertRaisesRegex(SemanticRepairPatchError, "protected_path"):
                    apply_semantic_repair_patch_documents(
                        stage="scene_set",
                        expected_review_input_digest="sha256:" + "a" * 64,
                        patch=_patch(
                            {
                                "op": "replace",
                                "artifact": "script.md",
                                "selector": "scene:20",
                                "path": path,
                                "expected_old": expected_old,
                                "value": value,
                                "reason_key": "semantic_source_mismatch",
                            }
                        ),
                        script=script,
                        manifest=manifest,
                        asset_plan=asset_plan,
                        allowed_selectors=["scene:20"],
                    )

    def test_rejects_event_reference_ids_atomically(self) -> None:
        for protected_key in (
            "primary_event_beat_id",
            "trigger_event_beat_id",
            "source_story_beat_id",
            "forbidden_future_event_beat_ids",
        ):
            with self.subTest(protected_key=protected_key):
                script, manifest, asset_plan = _documents()
                beat = script["scenes"][1]["scene_event"]["event_sequence"][0]
                manifest_beat = manifest["scenes"][1]["scene_event"]["event_sequence"][0]
                old = ["scene20_event_turn"] if protected_key.endswith("_ids") else "scene20_event_turn"
                beat[protected_key] = deepcopy(old)
                manifest_beat[protected_key] = deepcopy(old)
                before = deepcopy((script, manifest, asset_plan))
                with self.assertRaisesRegex(SemanticRepairPatchError, "protected_path"):
                    apply_semantic_repair_patch_documents(
                        stage="scene_set",
                        expected_review_input_digest="sha256:" + "a" * 64,
                        patch=_patch(
                            {
                                "op": "replace",
                                "artifact": "script.md",
                                "selector": "scene:20",
                                "path": (
                                    "scene_event.event_sequence"
                                    "[beat_id=scene20_event_turn]."
                                    + protected_key
                                ),
                                "expected_old": old,
                                "value": ["forged_event"] if isinstance(old, list) else "forged_event",
                                "reason_key": "semantic_event_reference_mismatch",
                            }
                        ),
                        script=script,
                        manifest=manifest,
                        asset_plan=asset_plan,
                        allowed_selectors=["scene:20"],
                    )
                self.assertEqual((script, manifest, asset_plan), before)

    def test_dotted_scene_and_beat_ids_are_patchable(self) -> None:
        dotted = _scene(31)
        dotted["scene_id"] = "3.1"
        beat = dotted["scene_event"]["event_sequence"][0]
        beat["beat_id"] = "scene3.1_event_turn"
        obligation = dotted["scene_intent"]["story_event_obligations"][0]
        obligation["event_id"] = "scene3.1_event_turn"
        obligation["source_event_beat_id"] = "scene3.1_event_turn"
        script = {"scenes": [deepcopy(dotted)]}
        manifest = deepcopy(script)
        asset_plan = {"assets": []}
        result = apply_semantic_repair_patch_documents(
            stage="scene_set",
            expected_review_input_digest="sha256:" + "a" * 64,
            patch=_patch(
                {
                    "op": "replace",
                    "artifact": "script.md",
                    "selector": "scene:3.1",
                    "path": (
                        "scene_event.event_sequence"
                        "[beat_id=scene3.1_event_turn].concrete_event.visible_action"
                    ),
                    "expected_old": "古い行動",
                    "value": "修正済みの行動",
                    "reason_key": "scene_set.causal_proof_weak",
                }
            ),
            script=script,
            manifest=manifest,
            asset_plan=asset_plan,
            allowed_selectors=["scene:3.1"],
        )
        self.assertEqual(result.changed_selectors, ("scene:3.1",))
        self.assertEqual(
            script["scenes"][0]["scene_event"]["event_sequence"][0][
                "visible_action"
            ],
            "修正済みの行動",
        )

    def test_patch_workspace_rejects_symlink_and_hardlink_outputs(self) -> None:
        for link_kind in ("symlink", "hardlink"):
            with self.subTest(link_kind=link_kind), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                run_dir = root / "run"
                run_dir.mkdir()
                external = root / "external.json"
                external.write_text("{}\n", encoding="utf-8")
                lease = tempfile.TemporaryDirectory(prefix="patch-security-")
                workspace_root = Path(lease.name)
                patch_path = workspace_root / "repair.patch.json"
                if link_kind == "symlink":
                    patch_path.symlink_to(external)
                else:
                    os.link(external, patch_path)
                identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
                with bind_run_root(run_dir, expected_identity=identity) as binding:
                    workspace = image_gen_app._BoundSemanticPatchWorkspace(
                        lease=lease,
                        run_dir=run_dir,
                        binding=binding,
                        root=workspace_root,
                        stage="scene_set",
                        round_number=1,
                        patch_path=patch_path,
                        root_identity=(
                            workspace_root.stat().st_dev,
                            workspace_root.stat().st_ino,
                        ),
                        immutable_sha256s={},
                        expected_review_input_digest="sha256:" + "a" * 64,
                    )
                    with self.assertRaisesRegex(RuntimeError, "unsafe"):
                        image_gen_app._verify_bound_semantic_patch_workspace(
                            workspace
                        )
                lease.cleanup()

    def test_patch_workspace_rejects_replaced_root_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            outer = Path(tmp)
            run_dir = outer / "run"
            run_dir.mkdir()
            lease = tempfile.TemporaryDirectory(prefix="patch-root-security-")
            workspace_root = Path(lease.name)
            root_identity = (
                workspace_root.stat().st_dev,
                workspace_root.stat().st_ino,
            )
            patch_path = workspace_root / "repair.patch.json"
            patch_path.write_text("{}\n", encoding="utf-8")
            external = outer / "external"
            external.mkdir()
            (external / "repair.patch.json").write_text("{}\n", encoding="utf-8")
            identity = (run_dir.stat().st_dev, run_dir.stat().st_ino)
            saved_root = workspace_root.with_name(workspace_root.name + "-saved")
            with bind_run_root(run_dir, expected_identity=identity) as binding:
                workspace = image_gen_app._BoundSemanticPatchWorkspace(
                    lease=lease,
                    run_dir=run_dir,
                    binding=binding,
                    root=workspace_root,
                    stage="scene_set",
                    round_number=1,
                    patch_path=patch_path,
                    root_identity=root_identity,
                    immutable_sha256s={},
                    expected_review_input_digest="sha256:" + "a" * 64,
                )
                workspace_root.rename(saved_root)
                workspace_root.symlink_to(external, target_is_directory=True)
                try:
                    with self.assertRaisesRegex(RuntimeError, "workspace root"):
                        image_gen_app._verify_bound_semantic_patch_workspace(
                            workspace
                        )
                finally:
                    workspace_root.unlink()
                    saved_root.rename(workspace_root)
            lease.cleanup()

    def test_patch_route_requires_canonical_digest_bound_scope(self) -> None:
        canonical = {
            "stage": "scene_set",
            "semantic_review_input_schema": SEMANTIC_REVIEW_INPUT_SCHEMA,
            "semantic_review_input_digest": "sha256:" + "a" * 64,
            "scope_binding_sha256": "b" * 64,
            "collection_sha256": "c" * 64,
            "prompt_sha256": "d" * 64,
            "source_artifact_digests": [
                {"path": "script.md", "sha256": "e" * 64}
            ],
        }
        self.assertTrue(
            image_gen_app._semantic_patch_route_enabled(
                "scene_set", ["scene:20"], scope=canonical
            )
        )
        legacy = {
            **canonical,
            "semantic_review_input_schema": LEGACY_SEMANTIC_REVIEW_INPUT_SCHEMA,
        }
        self.assertFalse(
            image_gen_app._semantic_patch_route_enabled(
                "scene_set", ["scene:20"], scope=legacy
            )
        )

    def test_nested_failure_selectors_collapse_to_stable_scene_or_cut_scope(self) -> None:
        for raw, expected in (
            (
                "scene20.scene_event.event_sequence[scene02_event_setup]",
                "scene:20",
            ),
            (
                "scene80.scene_contract_slice.required_beat_specs[scene08_event_turn].source_event_ids",
                "scene:80",
            ),
            (
                "scene3.1.scene_event.event_sequence[beat_id=scene3.1_event_turn].visible_action",
                "scene:3.1",
            ),
            ("scene20_cut01.cut_blueprint.visible_action", "scene20_cut01"),
            ("scene3.1.participants", "scene:3.1"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(
                    image_gen_app._canonical_semantic_repair_target_selector(raw),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
