from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import yaml

from toc.p400_rebuild import (
    CandidateBundle,
    P400RebuildError,
    apply_p400_rebuild,
    prepare_p400_rebuild,
    recover_p400_rebuild,
)
from toc.scene_acceptance_contract import (
    CRITERION_REGISTRY_VERSION,
    SCENE_ACCEPTANCE_CONTRACT_VERSION,
    SCENE_DRAFT_VERSION,
    criterion_registry_digest,
    criterion_registry_payload,
    digest_contract,
    digest_scene_draft,
    digest_scene_slice,
    domain_separated_digest,
    validate_scene_set_preflight,
)


class P400RebuildTests(unittest.TestCase):
    def _run_fixture(self, root: Path) -> Path:
        run_dir = root / "output" / "cinderella_20260821_1200"
        run_dir.mkdir(parents=True)
        files = {
            "research.md": "research bytes\n",
            "story.md": "story bytes\n",
            "visual_value.md": "visual value bytes\n",
            "script.md": "old script\n",
            "video_manifest.md": "old manifest\n",
            "p000_index.md": "old index\n",
            "state.txt": (
                "topic=cinderella\n"
                "status=P680\n"
                "slot.p520.status=done\n"
                "runtime.resume.p500.status=completed\n"
                "artifact.scene=/tmp/old-scene.json\n"
                "review.semantic.scene_set.status=passed\n"
                "---\n"
            ),
            "logs/review/semantic/scene_set.report.md": "old p400 report\n",
            "logs/image_generation_jobs/completed.json": (
                '{"jobId":"done","status":"completed"}\n'
            ),
            "assets/scenes/scene01.png": "old image bytes\n",
        }
        for relative, content in files.items():
            path = run_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return run_dir

    def _candidate(self, context) -> CandidateBundle:
        ledger = {"events": [{"id": "source_event_01", "summary": "灰の炉端"}]}
        ledger_bytes = (
            json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        ledger_path = (
            f"logs/authoring/staging/{context.generation_id}/source_ledger.json"
        )
        ledger_digest = "sha256:" + hashlib.sha256(ledger_bytes).hexdigest()
        contract = {
            "schema_version": SCENE_ACCEPTANCE_CONTRACT_VERSION,
            "generation_id": context.generation_id,
            "criterion_registry_version": CRITERION_REGISTRY_VERSION,
            "criterion_registry_sha256": criterion_registry_digest(),
            "source_bindings": {
                "authoring_source_ledger": {
                    "path": ledger_path,
                    "sha256": ledger_digest,
                }
            },
            "source_refs": [
                {
                    "source_ref_id": "source-event-1",
                    "artifact": "authoring_source_ledger",
                    "artifact_sha256": ledger_digest,
                    "pointer": "/events/0",
                    "expected_id": "source_event_01",
                }
            ],
            "canonical_events": [
                {
                    "event_id": "E01",
                    "canonical_order_index": 1,
                    "owner_scene_id": 10,
                    "required_beat_ids": ["scene10-beat-01"],
                    "source_ref_ids": ["source-event-1"],
                }
            ],
            "evidence_catalog": [
                {
                    "evidence_id": "evidence-hearth-ash",
                    "owner_scene_id": 10,
                    "element_id": "element-hearth-ash",
                    "source_ref_ids": ["source-event-1"],
                    "visible_form": "灰まみれの炉床",
                }
            ],
            "reveal_ledger": [],
            "handoff_chain": [],
            "transition_cues": [],
            "scenes": [
                {
                    "scene_id": 10,
                    "owned_event_ids": ["E01"],
                    "required_beat_specs": [
                        {
                            "beat_id": "scene10-beat-01",
                            "source_event_ids": ["E01"],
                            "beat_function": "setup",
                            "required_role_ids": ["protagonist"],
                            "required_character_ids": ["character-cinderella"],
                            "required_evidence_ids": ["evidence-hearth-ash"],
                            "required_non_replaceable_element_ids": [
                                "element-hearth-ash"
                            ],
                        }
                    ],
                    "role_bindings": [
                        {
                            "role_id": "protagonist",
                            "character_ids": ["character-cinderella"],
                            "required_for_beat_ids": ["scene10-beat-01"],
                        }
                    ],
                    "reveal_state_before": {},
                    "allowed_reveal_transition_ids": [],
                    "reveal_state_after": {},
                    "time_location_transition": {
                        "time_of_day": "morning",
                        "continuity_from_previous": "opening",
                        "transition_cue_required": False,
                        "transition_cue_ids": [],
                        "location_sequence": ["location-kitchen"],
                    },
                    "incoming_handoff_anchor_id": "story-opening",
                    "outgoing_handoff_anchor_id": "story-ending",
                    "causal_proof_contract": {
                        "cause_beat_id": "scene10-beat-01",
                        "action_beat_id": "scene10-beat-01",
                        "result_state_id": "state-after-scene-10",
                        "required_evidence_ids": ["evidence-hearth-ash"],
                    },
                    "non_replaceable_elements": [
                        {
                            "element_id": "element-hearth-ash",
                            "source_ref_ids": ["source-event-1"],
                            "required_evidence_ids": ["evidence-hearth-ash"],
                        }
                    ],
                }
            ],
        }
        contract["contract_digest"] = digest_contract(contract)
        draft = {
            "schema_version": SCENE_DRAFT_VERSION,
            "generation_id": context.generation_id,
            "scene_id": 10,
            "contract_digest": contract["contract_digest"],
            "scene_slice_digest": digest_scene_slice(contract, 10),
            "scene_intent": {"purpose": "灰の中の主人公を示す"},
            "scene_event": {
                "event_sequence": [
                    {
                        "beat_id": "scene10-beat-01",
                        "source_event_ids": ["E01"],
                        "role_ids": ["protagonist"],
                        "participant_character_ids": ["character-cinderella"],
                        "evidence_ids": ["evidence-hearth-ash"],
                        "required_non_replaceable_element_ids": [
                            "element-hearth-ash"
                        ],
                        "reveal_transition_ids": [],
                        "transition_cue_ids": [],
                        "incoming_handoff_anchor_ids": [],
                        "outgoing_handoff_anchor_ids": [],
                        "result_state_id": "state-after-scene-10",
                    }
                ]
            },
            "participants": [
                {
                    "character_id": "character-cinderella",
                    "role_ids": ["protagonist"],
                    "visibility": "visible",
                    "required_for_beat_ids": ["scene10-beat-01"],
                    "evidence_ids": ["evidence-hearth-ash"],
                }
            ],
            "handoff_refs": {"incoming": [], "outgoing": []},
        }
        validation = validate_scene_set_preflight(
            contract,
            [draft],
            source_artifacts={"authoring_source_ledger": ledger_bytes},
        )
        self.assertTrue(validation.valid, validation.to_dict())
        preflight = {
            "status": "passed",
            "generation_id": context.generation_id,
            "contract_digest": contract["contract_digest"],
            "criterion_registry_digest": criterion_registry_digest(),
            "source_digest": domain_separated_digest(
                "toc.scene_acceptance.sources.v1", contract["source_bindings"]
            ),
            "checks": [],
            "blocking_reason_keys": [],
            "scene_draft_digests": [digest_scene_draft(draft)],
            "preflight_digest": validation.metadata["preflight_digest"],
        }
        script = {
            "script_metadata": {"scene_acceptance_contract": "required_v1"},
            "scene_set_authoring_contract": contract,
            "authoring_preflight": preflight,
            "scenes": [{"scene_id": 10, "scene_acceptance_draft": draft}],
        }
        manifest = {
            "scene_acceptance_contract": {
                "schema_version": SCENE_ACCEPTANCE_CONTRACT_VERSION,
                "canonical_script_path": "script.md",
                "generation_id": context.generation_id,
                "contract_digest": contract["contract_digest"],
                "criterion_registry_sha256": criterion_registry_digest(),
                "preflight_status": "passed",
                "preflight_digest": preflight["preflight_digest"],
                "scene_slice_digests": {"10": draft["scene_slice_digest"]},
            },
            "scenes": [],
        }
        def md_yaml(title: str, value: dict) -> bytes:
            return (
                f"# {title}\n\n```yaml\n"
                + yaml.safe_dump(value, allow_unicode=True, sort_keys=False)
                + "```\n"
            ).encode("utf-8")

        return CandidateBundle(
            artifacts={
                "script.md": md_yaml("Script", script),
                "video_manifest.md": md_yaml("Manifest", manifest),
                "logs/authoring/scene_acceptance/contract.json": (
                    json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8"),
                "logs/authoring/scene_acceptance/preflight.json": (
                    json.dumps(preflight, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8"),
                "logs/authoring/scene_acceptance/criterion_registry.json": (
                    json.dumps(
                        {
                            "schema_version": CRITERION_REGISTRY_VERSION,
                            "criterion_registry_sha256": criterion_registry_digest(),
                            "criteria": criterion_registry_payload(),
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8"),
                ledger_path: ledger_bytes,
            },
        )

    def test_prepare_only_stages_candidate_and_binds_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)
            before = {
                relative: (run_dir / relative).read_bytes()
                for relative in ("script.md", "video_manifest.md", "state.txt")
            }

            plan = prepare_p400_rebuild(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-01",
                generation_id="generation-01",
                candidate_builder=self._candidate,
            )

            self.assertTrue(Path(plan.staging_dir, "plan.json").is_file())
            self.assertEqual(plan.schema_version, "p400_rebuild_plan_v1")
            self.assertEqual(plan.reuse_policy, "no_p500_plus_reuse_v1")
            self.assertTrue(plan.plan_token.startswith("sha256:"))
            self.assertEqual(
                before,
                {
                    relative: (run_dir / relative).read_bytes()
                    for relative in before
                },
            )
            self.assertEqual(
                plan.candidate["script_sha256"],
                "sha256:"
                + hashlib.sha256(
                    (Path(plan.staging_dir) / "script.md").read_bytes()
                ).hexdigest(),
            )

    def test_apply_publishes_exact_candidate_and_invalidates_downstream(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            second_root = root / "second"
            second_root.mkdir()
            run_dir = self._run_fixture(second_root)
            plan = prepare_p400_rebuild(
                repo_root=second_root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-02",
                generation_id="generation-02",
                candidate_builder=self._candidate,
            )
            expected_script = (Path(plan.staging_dir) / "script.md").read_bytes()
            expected_manifest = (
                Path(plan.staging_dir) / "video_manifest.md"
            ).read_bytes()

            checkpoint = apply_p400_rebuild(plan, plan_token=plan.plan_token)

            self.assertEqual(checkpoint.name, "checkpoint-02")
            self.assertEqual((run_dir / "script.md").read_bytes(), expected_script)
            self.assertEqual(
                (run_dir / "video_manifest.md").read_bytes(),
                expected_manifest,
            )
            self.assertFalse((run_dir / "assets/scenes/scene01.png").exists())
            self.assertFalse(
                (run_dir / "logs/image_generation_jobs/completed.json").exists()
            )
            checkpoint_artifact = checkpoint / "artifacts/assets/scenes/scene01.png"
            self.assertEqual(checkpoint_artifact.read_text(encoding="utf-8"), "old image bytes\n")
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.resume.p400.status=completed", state)
            self.assertIn("slot.p520.status=pending", state)
            self.assertIn("authoring.scene_set.contract.status=validated", state)
            self.assertIn(
                "authoring.scene_set.contract.digest="
                + plan.candidate["contract_semantic_sha256"],
                state,
            )
            self.assertIn(
                "authoring.scene_set.preflight.digest="
                + plan.candidate["preflight_semantic_sha256"],
                state,
            )
            # Historical reviewer state is preserved as opaque history; the
            # rebuild does not synthesize an invalidated reviewer verdict.
            self.assertNotIn("review.semantic.scene_set.status=invalidated", state)
            journal = json.loads((checkpoint / "publish.journal.json").read_text())
            self.assertEqual(journal["phase"], "completed")

            with self.assertRaises(P400RebuildError):
                apply_p400_rebuild(plan, plan_token=plan.plan_token)

    def test_apply_rejects_token_or_candidate_mutation_without_touching_active_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)
            plan = prepare_p400_rebuild(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-03",
                generation_id="generation-03",
                candidate_builder=self._candidate,
            )
            (run_dir / "logs/authoring/staging/generation-03/script.md").write_bytes(
                b"tampered\n"
            )
            with self.assertRaises(P400RebuildError):
                apply_p400_rebuild(plan, plan_token=plan.plan_token)
            self.assertEqual((run_dir / "script.md").read_text(), "old script\n")
            self.assertFalse((run_dir / "logs/resume/p400/checkpoint-03").exists())

    def test_bulk_job_hook_is_checked_at_prepare_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)
            with self.assertRaises(P400RebuildError):
                prepare_p400_rebuild(
                    repo_root=root,
                    run_dir=run_dir,
                    checkpoint_id="checkpoint-04",
                    generation_id="generation-04",
                    candidate_builder=self._candidate,
                    bulk_job_precondition=lambda _run: False,
                )

    def test_source_and_replace_digest_changes_are_rejected_at_apply(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)
            plan = prepare_p400_rebuild(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-digest",
                generation_id="generation-digest",
                candidate_builder=self._candidate,
            )
            (run_dir / "story.md").write_text("changed source\n", encoding="utf-8")
            with self.assertRaises(P400RebuildError):
                apply_p400_rebuild(plan, plan_token=plan.plan_token)
            self.assertFalse((run_dir / "logs/resume/p400/checkpoint-digest").exists())

            second_root = root / "second"
            second_root.mkdir()
            run_dir = self._run_fixture(second_root)
            plan = prepare_p400_rebuild(
                repo_root=second_root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-replace",
                generation_id="generation-replace",
                candidate_builder=self._candidate,
            )
            (run_dir / "script.md").write_text("changed old script\n", encoding="utf-8")
            with self.assertRaises(P400RebuildError):
                apply_p400_rebuild(plan, plan_token=plan.plan_token)

    def test_apply_bulk_job_hook_is_rechecked_under_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)
            plan = prepare_p400_rebuild(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-hook",
                generation_id="generation-hook",
                candidate_builder=self._candidate,
            )
            with self.assertRaises(P400RebuildError):
                apply_p400_rebuild(
                    plan,
                    plan_token=plan.plan_token,
                    bulk_job_precondition=lambda _run: False,
                )
            self.assertEqual((run_dir / "script.md").read_text(), "old script\n")

    def test_prepare_rejects_unrecognized_or_preserved_candidate_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)

            def unsafe_candidate(context):
                valid = self._candidate(context)
                return CandidateBundle(
                    artifacts={**valid.artifacts, "research.md": b"overwrite\n"}
                )

            with self.assertRaisesRegex(P400RebuildError, "not a p400 artifact"):
                prepare_p400_rebuild(
                    repo_root=root,
                    run_dir=run_dir,
                    checkpoint_id="checkpoint-allowlist",
                    generation_id="generation-allowlist",
                    candidate_builder=unsafe_candidate,
                )

    def test_prepare_rejects_status_only_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)

            def status_only_candidate(context):
                valid = self._candidate(context)
                return CandidateBundle(
                    artifacts={
                        **valid.artifacts,
                        "logs/authoring/scene_acceptance/preflight.json": (
                            b'{"status":"passed"}\n'
                        ),
                    }
                )

            with self.assertRaisesRegex(P400RebuildError, "disagrees with script"):
                prepare_p400_rebuild(
                    repo_root=root,
                    run_dir=run_dir,
                    checkpoint_id="checkpoint-semantic",
                    generation_id="generation-semantic",
                    candidate_builder=status_only_candidate,
                )

    def test_prepare_rejects_caller_declared_implementation_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)

            def forged_revision(context):
                valid = self._candidate(context)
                return CandidateBundle(
                    artifacts=valid.artifacts,
                    implementation_revision="sha256:" + "1" * 64,
                )

            with self.assertRaisesRegex(
                P400RebuildError,
                "implementation revision",
            ):
                prepare_p400_rebuild(
                    repo_root=root,
                    run_dir=run_dir,
                    checkpoint_id="checkpoint-revision",
                    generation_id="generation-revision",
                    candidate_builder=forged_revision,
                )

    def test_publish_failure_rolls_back_and_recovery_is_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)
            plan = prepare_p400_rebuild(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-05",
                generation_id="generation-05",
                candidate_builder=self._candidate,
            )

            def fail_after_first(_relative: str, index: int) -> None:
                if index == 1:
                    raise RuntimeError("injected publish failure")

            with self.assertRaises(P400RebuildError):
                apply_p400_rebuild(
                    plan,
                    plan_token=plan.plan_token,
                    publish_hook=fail_after_first,
                )
            self.assertEqual((run_dir / "script.md").read_text(), "old script\n")
            self.assertEqual((run_dir / "video_manifest.md").read_text(), "old manifest\n")
            self.assertTrue((run_dir / "assets/scenes/scene01.png").is_file())
            state = (run_dir / "state.txt").read_text(encoding="utf-8")
            self.assertIn("runtime.resume.p400.status=rollback", state)

    def test_recovery_rejects_tampered_completed_journal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)
            plan = prepare_p400_rebuild(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-06",
                generation_id="generation-06",
                candidate_builder=self._candidate,
            )
            checkpoint = apply_p400_rebuild(plan, plan_token=plan.plan_token)
            journal_path = checkpoint / "publish.journal.json"
            journal = json.loads(journal_path.read_text())
            journal["phase"] = "published"
            journal_path.write_text(json.dumps(journal) + "\n")

            with self.assertRaisesRegex(P400RebuildError, "journal phase"):
                recover_p400_rebuild(
                    run_dir,
                    "checkpoint-06",
                    action="rollback",
                )

            self.assertNotEqual((run_dir / "script.md").read_text(), "old script\n")
            self.assertFalse((run_dir / "assets/scenes/scene01.png").exists())
            self.assertIn(
                "runtime.resume.p400.status=completed",
                (run_dir / "state.txt").read_text(),
            )

    def test_recovery_never_completes_with_missing_active_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run_dir = self._run_fixture(root)
            plan = prepare_p400_rebuild(
                repo_root=root,
                run_dir=run_dir,
                checkpoint_id="checkpoint-missing-active",
                generation_id="generation-missing-active",
                candidate_builder=self._candidate,
            )
            apply_p400_rebuild(plan, plan_token=plan.plan_token)
            (run_dir / "script.md").unlink()

            with self.assertRaisesRegex(P400RebuildError, "active candidate"):
                recover_p400_rebuild(
                    run_dir,
                    "checkpoint-missing-active",
                    action="complete",
                )


if __name__ == "__main__":
    unittest.main()
