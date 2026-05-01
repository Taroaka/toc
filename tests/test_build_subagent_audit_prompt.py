import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-subagent-audit-prompt.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file

SPEC = importlib.util.spec_from_file_location("build_subagent_audit_prompt", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestBuildSubagentAuditPrompt(unittest.TestCase):
    def test_build_prompt_includes_required_artifacts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_prompt_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            prompt = MODULE.build_subagent_audit_prompt(stage="story", run_dir=run_dir, flow="toc-run")

            expected = (
                f"You are a contextless, audit-only verification subagent.\n\n"
                f"Audit the completed ToC stage `story` in run dir `{run_dir.resolve()}`.\n"
                f"Flow: `toc-run`.\n\n"
                "Do not generate content and do not edit story, script, manifest, or other content artifacts.\n"
                "You may refresh grounding audit artifacts by rerunning the helper command below.\n"
                "Do not rely on parent conversation context.\n\n"
                "If the helper command exits nonzero or any expected artifact is missing, report the missing items and stop; do not repair anything.\n\n"
                "First run this command:\n"
                f"`python scripts/audit-stage-grounding.py --stage story --run-dir {run_dir.resolve()}`\n\n"
                "Then inspect these artifacts directly:\n"
                f"- `{run_dir.resolve() / 'logs' / 'grounding' / 'story.json'}`\n"
                f"- `{run_dir.resolve() / 'logs' / 'grounding' / 'story.readset.json'}`\n"
                f"- `{run_dir.resolve() / 'logs' / 'grounding' / 'story.audit.json'}`\n"
                f"- `{run_dir.resolve() / 'state.txt'}`\n\n"
                "Use those files to verify:\n"
                "- the grounding report is `ready`\n"
                "- the readset is marked `verified_before_edit: true`\n"
                "- the readset covers the required global docs, stage docs, templates, and inputs\n"
                "- the audit report is `passed`\n\n"
                "Return only a compact structured result with these keys:\n"
                "status: passed|failed\n"
                "missing_artifacts: [...]\n"
                "missing_reads: [...]\n"
                "notes: [...]"
            )

            self.assertEqual(prompt, expected)

    def test_cli_defaults_flow_from_run_dir(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_prompt_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0001"
            (run_dir / "scenes" / "scene01").mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--stage",
                    "script",
                    "--run-dir",
                    str(run_dir),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertIn("Flow: `scene-series`.", result.stdout)
            self.assertIn("logs/grounding/script.json", result.stdout)
            self.assertIn("python scripts/audit-stage-grounding.py --stage script --run-dir", result.stdout)

    def test_cli_writes_prompt_artifact_and_state(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_prompt_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0002"
            run_dir.mkdir(parents=True, exist_ok=True)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--stage",
                    "manifest",
                    "--run-dir",
                    str(run_dir),
                    "--flow",
                    "immersive",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)

            prompt_path = run_dir / "logs" / "grounding" / "scene_implementation.subagent_prompt.md"
            self.assertTrue(prompt_path.exists())
            self.assertEqual(prompt_path.read_text(encoding="utf-8").strip(), result.stdout.strip())

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(
                state.get("stage.scene_implementation.subagent.prompt"),
                "logs/grounding/scene_implementation.subagent_prompt.md",
            )
            self.assertTrue(state.get("stage.scene_implementation.subagent.prompt.generated_at"))


if __name__ == "__main__":
    unittest.main()
