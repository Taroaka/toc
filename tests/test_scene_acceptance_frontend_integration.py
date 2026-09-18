from story_profile_fixture import _story_profile as fixture_story_profile
import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

REPO_ROOT = Path(__file__).resolve().parents[1]


def load_frontend_run_module():
    spec = importlib.util.spec_from_file_location(
        "scene_acceptance_frontend_run_under_test",
        REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestSceneAcceptanceFrontendIntegration(unittest.TestCase):
    def _profile(self, module):
        return module._duration_aware_profile(
            fixture_story_profile(
                "シンデレラ",
                "シンデレラ",
                variant_seed="scene-acceptance-integration",
            ),
            target_duration_seconds=300,
        )

    def test_scene_set_preflight_completes_before_first_cut_plan(self) -> None:
        module = load_frontend_run_module()
        profile = self._profile(module)
        preflight_completed = False
        original_preflight = module._run_scene_acceptance_preflight
        original_cut_planner = module._scene_cut_coverage_plan

        def observe_preflight(*args, **kwargs):
            nonlocal preflight_completed
            result = original_preflight(*args, **kwargs)
            self.assertEqual(result["status"], "passed", result)
            preflight_completed = True
            return result

        def observe_cut_planner(*args, **kwargs):
            self.assertTrue(
                preflight_completed,
                "cut planning started before the whole scene set passed preflight",
            )
            return original_cut_planner(*args, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            with (
                patch.object(
                    module,
                    "_run_scene_acceptance_preflight",
                    side_effect=observe_preflight,
                ),
                patch.object(
                    module,
                    "_scene_cut_coverage_plan",
                    side_effect=observe_cut_planner,
                ),
            ):
                script, _manifest, _selectors = module._build_script_and_manifest(
                    "シンデレラ",
                    run_dir,
                    "2099-01-01T00:00:00+09:00",
                    profile,
                )

        self.assertTrue(preflight_completed)
        self.assertEqual(script["authoring_preflight"]["status"], "passed")

    def test_new_run_publishes_contract_and_digest_projection(self) -> None:
        module = load_frontend_run_module()
        profile = self._profile(module)

        with tempfile.TemporaryDirectory() as tmp:
            script, manifest, _selectors = module._build_script_and_manifest(
                "シンデレラ",
                Path(tmp),
                "2099-01-01T00:00:00+09:00",
                profile,
            )

        self.assertEqual(
            script["script_metadata"]["scene_acceptance_contract"],
            "required_v1",
        )
        contract = script["scene_set_authoring_contract"]
        self.assertEqual(
            contract["schema_version"],
            "scene_set_authoring_contract_v1",
        )
        self.assertTrue(contract["contract_digest"].startswith("sha256:"))
        self.assertEqual(script["authoring_preflight"]["status"], "passed")
        self.assertEqual(
            script["authoring_preflight"]["contract_digest"],
            contract["contract_digest"],
        )

        projection = manifest["scene_acceptance_contract"]
        self.assertEqual(projection["contract_digest"], contract["contract_digest"])
        self.assertEqual(projection["canonical_script_path"], "script.md")
        self.assertNotIn("scene_set_authoring_contract", manifest)
        for scene in manifest["scenes"]:
            self.assertNotIn("scene_acceptance_draft", scene)
            self.assertNotIn(
                "scene_acceptance_prompt_packet",
                scene["scene_generation"],
            )
            self.assertEqual(
                scene["scene_acceptance_binding"]["contract_digest"],
                contract["contract_digest"],
            )

        contract_scene_ids = [item["scene_id"] for item in contract["scenes"]]
        self.assertEqual(
            contract_scene_ids,
            [scene["scene_id"] for scene in script["scenes"]],
        )
        for scene in script["scenes"]:
            draft = scene["scene_acceptance_draft"]
            self.assertEqual(draft["schema_version"], "scene_draft_v1")
            self.assertEqual(draft["contract_digest"], contract["contract_digest"])
            self.assertTrue(draft["scene_slice_digest"].startswith("sha256:"))

    def test_interrupted_canonical_pair_publish_rolls_back_exact_generation(self) -> None:
        module = load_frontend_run_module()
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            generation_id = "scene-authoring-recovery-test"
            staging = (
                run_dir / "logs" / "authoring" / "staging" / generation_id
            )
            staging.mkdir(parents=True)
            script_bytes = b"new script generation\n"
            manifest_bytes = b"new manifest generation\n"
            (run_dir / "script.md").write_bytes(script_bytes)
            journal = {
                "schema_version": "scene_authoring_publish_journal_v1",
                "generation_id": generation_id,
                "status": "publishing",
                "canonical_targets": ["script.md", "video_manifest.md"],
                "canonical_target_sha256": {
                    "script.md": "sha256:"
                    + hashlib.sha256(script_bytes).hexdigest(),
                    "video_manifest.md": "sha256:"
                    + hashlib.sha256(manifest_bytes).hexdigest(),
                },
                "previous_canonical": {
                    "script.md": {
                        "exists": False,
                        "sha256": None,
                        "backup_path": None,
                    },
                    "video_manifest.md": {
                        "exists": False,
                        "sha256": None,
                        "backup_path": None,
                    },
                },
            }
            (staging / "publish.journal.json").write_text(
                json.dumps(journal) + "\n",
                encoding="utf-8",
            )

            module._recover_interrupted_scene_pair_publish(
                run_dir,
                root_identity=module.directory_identity_nofollow(run_dir),
            )

            self.assertFalse((run_dir / "script.md").exists())
            recovered = json.loads(
                (staging / "publish.journal.json").read_text(encoding="utf-8")
            )
            self.assertEqual(recovered["status"], "rolled_back")

    def test_invalid_scene_set_stops_before_cut_materialization(self) -> None:
        module = load_frontend_run_module()
        profile = self._profile(module)
        original_event_builder = module._scene_event_for_cut_design
        cut_planner = Mock(side_effect=AssertionError("cut planner must not run"))
        call_count = 0

        def invalid_first_scene(*args, **kwargs):
            nonlocal call_count
            result = original_event_builder(*args, **kwargs)
            call_count += 1
            if call_count == 1:
                result["event_sequence"] = []
            return result

        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch.object(
                    module,
                    "_scene_event_for_cut_design",
                    side_effect=invalid_first_scene,
                ),
                patch.object(
                    module,
                    "_scene_cut_coverage_plan",
                    cut_planner,
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "no authored event beat"):
                    module._build_script_and_manifest(
                        "シンデレラ",
                        Path(tmp),
                        "2099-01-01T00:00:00+09:00",
                        profile,
                    )

        cut_planner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
