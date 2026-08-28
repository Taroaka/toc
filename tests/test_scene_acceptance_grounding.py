"""Grounding/template contracts for scene acceptance shift-left authoring.

These tests deliberately inspect only the canonical docs and templates.  They
are useful before the runtime validator exists: a fresh agent must be able to
discover the contract, its digest/state rules, and the planner/author/reviewer
boundary without relying on a previous conversation.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_first_yaml_fence(path: Path) -> dict:
    match = re.search(r"```yaml\n(.*?)\n```", path.read_text(encoding="utf-8"), re.DOTALL)
    if not match:
        raise AssertionError(f"no yaml fence found in {path}")
    return yaml.safe_load(match.group(1))


class TestSceneAcceptanceGrounding(unittest.TestCase):
    def test_script_template_is_contract_first_and_machine_readable(self) -> None:
        template = _load_yaml(REPO_ROOT / "workflow" / "script-template.yaml")
        contract = template["scene_set_authoring_contract"]

        self.assertEqual(contract["schema_version"], "scene_set_authoring_contract_v1")
        for key in (
            "generation_id",
            "criterion_registry_version",
            "criterion_registry_sha256",
            "source_bindings",
            "source_refs",
            "canonical_events",
            "evidence_catalog",
            "reveal_ledger",
            "handoff_chain",
            "transition_cues",
            "scenes",
        ):
            with self.subTest(key=key):
                self.assertIn(key, contract)

        self.assertNotIn("authoring_preflight", contract)
        preflight = template["authoring_preflight"]
        self.assertEqual(preflight["status"], "pending")
        self.assertIn("contract_digest", preflight)
        self.assertIn("preflight_digest", preflight)
        self.assertEqual(template["scenes"][0]["scene_contract_slice"]["schema_version"], "scene_contract_slice_v1")

    def test_scene_outline_contains_frozen_slice_and_computed_only_preflight(self) -> None:
        template = _load_yaml(REPO_ROOT / "workflow" / "scene-outline-template.yaml")
        ref = template["scene_set_authoring_contract_ref"]
        self.assertEqual(ref["schema_version"], "scene_set_authoring_contract_ref_v1")
        for key in ("path", "generation_id", "contract_digest", "criterion_registry_sha256", "source_digest"):
            with self.subTest(key=key):
                self.assertIn(key, ref)

        scene = template["scenes"][0]
        slice_ = scene["scene_contract_slice"]
        for key in (
            "canonical_event_ids",
            "required_beat_specs",
            "role_bindings",
            "reveal_state_before",
            "allowed_reveal_transition_ids",
            "reveal_state_after",
            "time_location_transition",
            "incoming_handoff_anchor_id",
            "outgoing_handoff_anchor_id",
            "causal_proof_contract",
            "non_replaceable_elements",
        ):
            with self.subTest(key=key):
                self.assertIn(key, slice_)

        preflight = scene["authoring_preflight"]
        self.assertEqual(preflight["schema_version"], "scene_authoring_preflight_v1")
        self.assertEqual(preflight["status"], "pending")
        self.assertNotEqual(preflight["status"], "passed")

    def test_video_manifest_projects_digests_without_second_contract_root(self) -> None:
        template = _load_first_yaml_fence(REPO_ROOT / "workflow" / "video-manifest-template.md")
        projection = template["scene_acceptance_projection"]
        self.assertEqual(projection["schema_version"], "scene_acceptance_projection_v1")
        for key in (
            "source_script",
            "generation_id",
            "contract_digest",
            "criterion_registry_sha256",
            "source_digest",
            "preflight_digest",
            "scene_slice_digests",
        ):
            with self.subTest(key=key):
                self.assertIn(key, projection)
        self.assertNotIn("canonical_events", projection)
        self.assertNotIn("reveal_ledger", projection)
        scene_projection = template["scenes"][0]["scene_acceptance_projection"]
        self.assertEqual(scene_projection["schema_version"], "scene_acceptance_scene_projection_v1")
        self.assertIn("scene_slice_digest", scene_projection)
        self.assertIn("preflight_digest", scene_projection)

    def test_stage_grounding_readset_includes_contract_docs_and_templates(self) -> None:
        grounding = _load_yaml(REPO_ROOT / "workflow" / "stage-grounding.yaml")
        self.assertGreaterEqual(grounding["contract_version"], 6)

        script = grounding["stages"]["script"]
        for path in (
            "docs/story-creation.md",
            "docs/data-contracts.md",
            "docs/implementation/agent-roles-and-prompts.md",
        ):
            with self.subTest(stage="script", path=path):
                self.assertIn(path, script["required_docs"])
        for path in (
            "workflow/script-template.yaml",
            "workflow/scene-outline-template.yaml",
            "workflow/video-manifest-template.md",
        ):
            with self.subTest(stage="script", path=path):
                self.assertIn(path, script["required_templates"])

        scene_impl = grounding["stages"]["scene_implementation"]
        for path in (
            "docs/data-contracts.md",
            "docs/implementation/agent-roles-and-prompts.md",
        ):
            with self.subTest(stage="scene_implementation", path=path):
                self.assertIn(path, scene_impl["required_docs"])
        self.assertIn("workflow/scene-outline-template.yaml", scene_impl["required_templates"])

    def test_docs_define_history_free_prompt_and_independent_review_boundary(self) -> None:
        story = (REPO_ROOT / "docs" / "story-creation.md").read_text(encoding="utf-8")
        data_contracts = (REPO_ROOT / "docs" / "data-contracts.md").read_text(encoding="utf-8")
        roles = (REPO_ROOT / "docs" / "implementation" / "agent-roles-and-prompts.md").read_text(encoding="utf-8")

        for text, required in (
            (story, ("Scene acceptance", "scene_set_authoring_contract_v1", "authoring_preflight", "会話履歴")),
            (data_contracts, ("Scene acceptance contract", "artifact.scene_set_authoring_contract.digest", "shift_left_escape")),
            (roles, ("Scene-set Contract Planner", "Scene Author", "Independent Contextless Reviewer", "scene_authoring_prompt_packet_v1")),
        ):
            for marker in required:
                with self.subTest(marker=marker):
                    self.assertIn(marker, text)

    def test_templates_explain_legacy_and_exact_projection_in_comments(self) -> None:
        script = (REPO_ROOT / "workflow" / "script-template.yaml").read_text(encoding="utf-8")
        scene = (REPO_ROOT / "workflow" / "scene-outline-template.yaml").read_text(encoding="utf-8")
        manifest = (REPO_ROOT / "workflow" / "video-manifest-template.md").read_text(encoding="utf-8")
        for text in (script, scene, manifest):
            with self.subTest(template="contract-first comments"):
                self.assertIn("会話履歴", text)
                self.assertIn("read-only projection", text)
                self.assertIn("digest", text)
        self.assertIn("契約全体を複製しない", manifest)


if __name__ == "__main__":
    unittest.main()
