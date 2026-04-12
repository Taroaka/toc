import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import StageGroundingError, grounding_validation, run_stage_grounding
from toc.harness import append_state_snapshot, parse_state_file


def _run_grounding(run_dir: Path, stage: str, *, flow: str = "toc-run") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "resolve-stage-grounding.py"),
            "--stage",
            stage,
            "--run-dir",
            str(run_dir),
            "--flow",
            flow,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_audit(run_dir: Path, stage: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "audit-stage-grounding.py"),
            "--stage",
            stage,
            "--run-dir",
            str(run_dir),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_prepare(run_dir: Path, stage: str, *, flow: str = "toc-run") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "prepare-stage-context.py"),
            "--stage",
            stage,
            "--run-dir",
            str(run_dir),
            "--flow",
            flow,
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _run_select_playbooks(run_dir: Path, stage: str, *, flow: str = "toc-run", selects: list[str] | None = None, select_all: bool = False) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "select-stage-playbooks.py"),
        "--stage",
        stage,
        "--run-dir",
        str(run_dir),
    ]
    if flow is not None:
        cmd.extend(["--flow", flow])
    for item in selects or []:
        cmd.extend(["--select", item])
    if select_all:
        cmd.append("--select-all")
    return subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _good_story_yaml() -> str:
    return (
        "```yaml\n"
        "selection:\n"
        "  candidates:\n"
        "    - candidate_id: \"A\"\n"
        "      logline: \"王道案\"\n"
        "      why_it_scores: [\"clear\"]\n"
        "      score_hint:\n"
        "        engagement: 0.9\n"
        "        coherence: 0.9\n"
        "        production_fit: 0.9\n"
        "      requires_hybridization_approval: false\n"
        "  chosen_candidate_id: \"A\"\n"
        "  rationale: \"最も安定している\"\n"
        "hybridization:\n"
        "  approval_status: \"not_needed\"\n"
        "script:\n"
        "  scenes:\n"
        "    - scene_id: 1\n"
        "      phase: \"opening\"\n"
        "      narration: \"導入です。\"\n"
        "      visual: \"導入の情景\"\n"
        "      research_refs: [\"research.story_baseline.canonical_synopsis\"]\n"
        "```\n"
    )


class TestStageGrounding(unittest.TestCase):
    def test_research_grounding_ready_without_run_inputs(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = _run_grounding(run_dir, "research")

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            report = json.loads((run_dir / "logs" / "grounding" / "research.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["required_paths"]["inputs"], [])
            self.assertIn("docs/system-architecture.md", report["required_paths"]["global_docs"])
            self.assertTrue((run_dir / "logs" / "grounding" / "research.readset.json").exists())
            self.assertTrue((run_dir / "logs" / "grounding" / "research.audit.json").exists())

    def test_story_grounding_fails_when_research_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0001"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = _run_grounding(run_dir, "story")

            self.assertEqual(result.returncode, 1)
            report = json.loads((run_dir / "logs" / "grounding" / "story.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "missing_inputs")
            self.assertIn("research.md", [entry["path"] for entry in report["missing_paths"]])
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["stage.story.grounding.status"], "missing_inputs")

    def test_script_grounding_requires_approved_story(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0002"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "story.md").write_text(_good_story_yaml(), encoding="utf-8")

            result = _run_grounding(run_dir, "script")

            self.assertEqual(result.returncode, 1)
            report = json.loads((run_dir / "logs" / "grounding" / "script.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "missing_inputs")
            self.assertEqual(report["approved_input_checks"][0]["review_key"], "review.story.status")
            self.assertEqual(report["approved_input_checks"][0]["policy_key"], "review.policy.story")
            self.assertTrue(report["approved_input_checks"][0]["approval_required"])
            self.assertFalse(report["approved_input_checks"][0]["passed"])

    def test_script_grounding_allows_optional_story_review_policy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0002b"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "story.md").write_text(_good_story_yaml(), encoding="utf-8")
            append_state_snapshot(run_dir / "state.txt", {"review.policy.story": "optional"})

            result = _run_grounding(run_dir, "script")

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            report = json.loads((run_dir / "logs" / "grounding" / "script.json").read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "ready")
            self.assertFalse(report["approved_input_checks"][0]["approval_required"])
            self.assertEqual(report["review_policy"]["story"], "optional")

    def test_manifest_alias_reads_image_prompt_grounding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0003"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "story.md").write_text(_good_story_yaml(), encoding="utf-8")
            (run_dir / "video_manifest.md").write_text("```yaml\nscenes: []\n```\n", encoding="utf-8")
            append_state_snapshot(run_dir / "state.txt", {"review.story.status": "approved"})

            result = _run_grounding(run_dir, "image_prompt")

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            validation = grounding_validation(run_dir, "manifest")
            self.assertTrue(validation["report_exists"])
            self.assertTrue(validation["report_ready"])
            self.assertTrue(validation["readset_exists"])
            self.assertTrue(validation["audit_exists"])
            self.assertTrue(validation["audit_passed"])
            self.assertEqual(validation["state_status"], "ready")

    def test_audit_cli_rewrites_passed_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0003b"
            run_dir.mkdir(parents=True, exist_ok=True)

            _run_grounding(run_dir, "research")
            result = _run_audit(run_dir, "research")

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            audit = json.loads((run_dir / "logs" / "grounding" / "research.audit.json").read_text(encoding="utf-8"))
            self.assertEqual(audit["status"], "passed")
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["stage.research.audit.status"], "passed")

    def test_run_stage_grounding_marks_failed_after_retry(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0004"
            run_dir.mkdir(parents=True, exist_ok=True)

            with self.assertRaises(StageGroundingError):
                run_stage_grounding(run_dir, "story", flow="toc-run", retries=1)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["stage.story.grounding.status"], "missing_inputs")
            self.assertEqual(state["stage.story.status"], "failed")
            self.assertEqual(state["last_error"], "grounding_failed:story:missing_inputs")

    def test_scene_dir_grounding_inherits_parent_run_inputs_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            root_run_dir = Path(td) / "output" / "momotaro_20990101_0005"
            scene_dir = root_run_dir / "scenes" / "scene01"
            scene_dir.mkdir(parents=True, exist_ok=True)

            (root_run_dir / "story.md").write_text(_good_story_yaml(), encoding="utf-8")
            (root_run_dir / "video_manifest.md").write_text("```yaml\nscenes: []\n```\n", encoding="utf-8")
            (scene_dir / "video_manifest.md").write_text("```yaml\nscenes: []\n```\n", encoding="utf-8")
            append_state_snapshot(root_run_dir / "state.txt", {"review.story.status": "approved"})

            report = run_stage_grounding(scene_dir, "image_prompt", flow="scene-series", retries=0, mark_stage_failure=False)

            self.assertEqual(report["status"], "ready")
            self.assertEqual(report["parent_run_dir"], str(root_run_dir.resolve()))
            story_entry = next(entry for entry in report["resolved_paths"]["inputs"] if entry["path"] == "story.md")
            self.assertEqual(story_entry["source"], "parent_run_dir")
            scene_state = parse_state_file(scene_dir / "state.txt")
            self.assertEqual(scene_state["stage.image_prompt.grounding.status"], "ready")
            self.assertEqual(scene_state["stage.image_prompt.audit.status"], "passed")

    def test_prepare_stage_context_returns_serialized_readset_for_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0006"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "story.md").write_text(_good_story_yaml(), encoding="utf-8")
            append_state_snapshot(run_dir / "state.txt", {"review.policy.story": "optional"})

            result = _run_prepare(run_dir, "script")

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stage"], "script")
            self.assertEqual(payload["flow"], "toc-run")
            self.assertEqual(payload["read_order"], ["global_docs", "stage_docs", "templates", "inputs"])
            self.assertTrue(payload["verified_before_edit"])
            self.assertTrue(payload["readset_path"].endswith("script.readset.json"))
            self.assertTrue(Path(payload["readset_path"]).exists())
            self.assertTrue(Path(payload["audit_path"]).exists())
            self.assertEqual(payload["selected_optional_playbooks"], [])
            self.assertEqual(payload["selected_optional_playbook_paths"], [])
            self.assertEqual(payload["selected_optional_playbook_count"], 0)
            self.assertEqual(payload["playbooks_report_path"], "")

    def test_select_stage_playbooks_records_selected_subset_for_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0006b"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = _run_select_playbooks(
                run_dir,
                "script",
                selects=["workflow/playbooks/script/hero-journey-beat-first.md"],
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            report_path = run_dir / "logs" / "grounding" / "script.playbooks.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["selection_mode"], "explicit")
            self.assertEqual(report["selected_count"], 1)
            self.assertEqual(report["selected_paths"], ["workflow/playbooks/script/hero-journey-beat-first.md"])
            self.assertEqual(report["selected_optional_playbooks"][0]["path"], "workflow/playbooks/script/hero-journey-beat-first.md")
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state["stage.script.playbooks.report"], "logs/grounding/script.playbooks.json")
            self.assertEqual(state["stage.script.playbooks.selected_count"], "1")

    def test_select_stage_playbooks_rejects_non_optional_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0006c"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = _run_select_playbooks(
                run_dir,
                "script",
                selects=["docs/story-creation.md"],
            )

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["status"], "invalid_selection")
            self.assertIn("docs/story-creation.md", payload["invalid_paths"])

    def test_select_stage_playbooks_supports_select_all_for_script(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0006cc"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = _run_select_playbooks(run_dir, "script", select_all=True)

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            report = json.loads((run_dir / "logs" / "grounding" / "script.playbooks.json").read_text(encoding="utf-8"))
            self.assertEqual(report["selection_mode"], "all")
            self.assertEqual(report["selected_count"], len(report["available_optional_playbooks"]))
            self.assertGreater(report["selected_count"], 0)

    def test_prepare_stage_context_returns_selected_optional_playbooks_when_report_exists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0006d"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "story.md").write_text(_good_story_yaml(), encoding="utf-8")
            append_state_snapshot(run_dir / "state.txt", {"review.policy.story": "optional"})

            select_result = _run_select_playbooks(
                run_dir,
                "script",
                selects=[
                    "workflow/playbooks/script/hero-journey-beat-first.md",
                    "workflow/playbooks/script/visual-value-midroll-pass.md",
                ],
            )
            self.assertEqual(select_result.returncode, 0, msg=select_result.stderr)

            result = _run_prepare(run_dir, "script")

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["selected_optional_playbook_count"], 2)
            self.assertEqual(
                [entry["path"] for entry in payload["selected_optional_playbooks"]],
                [
                    "workflow/playbooks/script/hero-journey-beat-first.md",
                    "workflow/playbooks/script/visual-value-midroll-pass.md",
                ],
            )
            self.assertTrue(payload["playbooks_report_path"].endswith("script.playbooks.json"))
            self.assertTrue(Path(payload["playbooks_report_path"]).exists())

    def test_prepare_stage_context_fails_when_stage_inputs_missing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_grounding_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0007"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = _run_prepare(run_dir, "story")

            self.assertEqual(result.returncode, 1)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["stage"], "story")
            self.assertEqual(payload["status"], "missing_inputs")
            self.assertIn("research.md", [entry["path"] for entry in payload["missing_paths"]])


if __name__ == "__main__":
    unittest.main()
