import subprocess
import sys
import unittest
from pathlib import Path


def _merge_state(path: Path) -> dict[str, str]:
    merged: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        merged[k.strip()] = v.strip()
    return merged


class TestTocStateScript(unittest.TestCase):
    def test_ensure_append_show(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_state_test_") as td:
            run_dir = Path(td) / "out" / "topic_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            manifest = run_dir / "video_manifest.md"
            manifest.write_text(
                "\n".join(
                    [
                        "# Manifest",
                        "",
                        "```yaml",
                        'video_metadata:',
                        '  topic: "テストトピック"',
                        "scenes: []",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [sys.executable, "scripts/toc-state.py", "ensure", "--run-dir", str(run_dir), "--manifest", str(manifest)],
                check=True,
                capture_output=True,
                text=True,
            )

            state_path = run_dir / "state.txt"
            self.assertTrue(state_path.exists())
            self.assertTrue((run_dir / "p000_index.md").exists())
            self.assertTrue((run_dir / "run_status.json").exists())
            st = _merge_state(state_path)
            self.assertEqual(st.get("topic"), "テストトピック")
            self.assertEqual(st.get("runtime.stage"), "init")
            self.assertNotIn("gate.video_review", st)
            self.assertIn("artifact.video_manifest", st)
            self.assertIn("artifact.run_index", st)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-state.py",
                    "append",
                    "--run-dir",
                    str(run_dir),
                    "--set",
                    "runtime.stage=render",
                    "--set",
                    "runtime.render.status=started",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            st = _merge_state(state_path)
            self.assertEqual(st.get("runtime.stage"), "render")
            self.assertEqual(st.get("runtime.render.status"), "started")
            self.assertTrue((run_dir / "run_status.json").exists())

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-state.py",
                    "set-slot",
                    "--run-dir",
                    str(run_dir),
                    "--slot",
                    "p570",
                    "--status",
                    "skipped",
                    "--requirement",
                    "optional",
                    "--skip-reason",
                    "asset stage not needed for draft",
                    "--note",
                    "user deferred reusable assets",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            st = _merge_state(state_path)
            self.assertEqual(st.get("slot.p570.status"), "skipped")
            self.assertEqual(st.get("slot.p570.requirement"), "optional")
            self.assertEqual(st.get("slot.p570.skip_reason"), "asset stage not needed for draft")
            self.assertEqual(st.get("slot.p570.note"), "user deferred reusable assets")

            r = subprocess.run(
                [sys.executable, "scripts/toc-state.py", "show", "--run-dir", str(run_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertNotIn("Review:", r.stdout)
            self.assertNotIn("Image prompt gate:", r.stdout)
            self.assertIn("Render: started", r.stdout)
            self.assertIn("Run status:", r.stdout)

            index_text = (run_dir / "p000_index.md").read_text(encoding="utf-8")
            self.assertNotIn("p540", index_text)
            self.assertIn("#### p570 Asset Continuity Check", index_text)
            self.assertIn("#### p740 Duration Fit Gate", index_text)

    def test_set_slot_rejects_unknown_slot_and_invalid_enums(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_state_slot_validation_") as td:
            run_dir = Path(td) / "out" / "topic_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "state.txt").write_text("topic=test\n---\n", encoding="utf-8")

            bad_slot = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-state.py",
                    "set-slot",
                    "--run-dir",
                    str(run_dir),
                    "--slot",
                    "p999",
                    "--status",
                    "done",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(bad_slot.returncode, 0)
            self.assertIn("Invalid --slot", bad_slot.stderr)

            bad_status = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-state.py",
                    "set-slot",
                    "--run-dir",
                    str(run_dir),
                    "--slot",
                    "p570",
                    "--status",
                    "whatever",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(bad_status.returncode, 0)
            self.assertIn("Invalid --status", bad_status.stderr)

            bad_requirement = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-state.py",
                    "set-slot",
                    "--run-dir",
                    str(run_dir),
                    "--slot",
                    "p570",
                    "--requirement",
                    "maybe",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(bad_requirement.returncode, 0)
            self.assertIn("Invalid --requirement", bad_requirement.stderr)

            retired = subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-state.py",
                    "set-slot",
                    "--run-dir",
                    str(run_dir),
                    "--slot",
                    "p230",
                    "--status",
                    "done",
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(retired.returncode, 0)
            self.assertIn("Invalid --slot", retired.stderr)

            removed_command = subprocess.run(
                [sys.executable, "scripts/toc-state.py", "approve-video", "--run-dir", str(run_dir)],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(removed_command.returncode, 0)

    def test_sync_keeps_eval_report_out_of_production_projection(self) -> None:
        import json
        import tempfile

        with tempfile.TemporaryDirectory(prefix="toc_state_sync_") as td:
            run_dir = Path(td) / "out" / "topic_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "timestamp=2099-01-01T00:00:00+09:00",
                        "job_id=JOB_2099-01-01_000000",
                        "topic=同期テスト",
                        "status=DONE",
                        "runtime.stage=done",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "eval_report.json").write_text(
                json.dumps({"overall": {"passed": True}}, ensure_ascii=False),
                encoding="utf-8",
            )

            subprocess.run(
                [sys.executable, "scripts/toc-state.py", "sync", "--run-dir", str(run_dir)],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads((run_dir / "run_status.json").read_text(encoding="utf-8"))
            self.assertNotIn("eval_report", payload)
            self.assertTrue((run_dir / "p000_index.md").exists())


if __name__ == "__main__":
    unittest.main()
