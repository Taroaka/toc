"""Grounding/template contracts for scene acceptance authoring.

These tests deliberately inspect only the canonical docs and templates.  They
are useful before the runtime validator exists: a fresh agent must be able to
discover the contract and its digest/state rules without relying on a previous
conversation.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class TestSceneAcceptanceGrounding(unittest.TestCase):
    def test_script_template_is_contract_first_and_machine_readable(self) -> None:
        template = _load_yaml(REPO_ROOT / "workflow" / "script-template.yaml")
        contract = template["scene_set_authoring_contract"]

        self.assertEqual(contract["schema_version"], "scene_set_authoring_contract_v1")
        for key in (
            "generation_id",
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
        self.assertIn("pending", str(preflight["status"]).split("|"))
        self.assertIn("contract_digest", preflight)
        self.assertIn("preflight_digest", preflight)

    def test_scene_outline_contains_frozen_slice_and_computed_only_preflight(self) -> None:
        template = _load_yaml(REPO_ROOT / "workflow" / "scene-outline-template.yaml")
        ref = template["scene_set_authoring_contract_ref"]
        self.assertEqual(ref["schema_version"], "scene_set_authoring_contract_ref_v1")
        for key in ("path", "generation_id", "contract_digest", "source_digest"):
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
        self.assertIn("pending", str(preflight["status"]).split("|"))
        self.assertNotEqual(preflight["status"], "passed")

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


if __name__ == "__main__":
    unittest.main()
