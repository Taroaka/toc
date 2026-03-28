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
    def test_ensure_append_approve_show(self) -> None:
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
            self.assertTrue((run_dir / "run_status.json").exists())
            st = _merge_state(state_path)
            self.assertEqual(st.get("topic"), "テストトピック")
            self.assertEqual(st.get("runtime.stage"), "init")
            self.assertIn("artifact.video_manifest", st)

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
                    "approve-image-prompts",
                    "--run-dir",
                    str(run_dir),
                    "--note",
                    "human checked",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            st = _merge_state(state_path)
            self.assertEqual(st.get("review.image_prompt.status"), "approved")
            self.assertEqual(st.get("review.image_prompt.note"), "human checked")
            self.assertIn("review.image_prompt.at", st)

            subprocess.run(
                [
                    sys.executable,
                    "scripts/toc-state.py",
                    "approve-video",
                    "--run-dir",
                    str(run_dir),
                    "--note",
                    "OK",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            st = _merge_state(state_path)
            self.assertEqual(st.get("review.video.status"), "approved")
            self.assertEqual(st.get("review.video.note"), "OK")
            self.assertIn("review.video.at", st)

            r = subprocess.run(
                [sys.executable, "scripts/toc-state.py", "show", "--run-dir", str(run_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("Review: approved", r.stdout)
            self.assertIn("Image prompt gate:", r.stdout)
            self.assertIn("Render: started", r.stdout)
            self.assertIn("Run status:", r.stdout)

    def test_sync_embeds_eval_report(self) -> None:
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
            self.assertIn("eval_report", payload)
            self.assertEqual(payload["eval_report"]["overall"]["passed"], True)


if __name__ == "__main__":
    unittest.main()
