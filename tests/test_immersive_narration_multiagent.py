import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from toc.harness import load_structured_document

REPO_ROOT = Path(__file__).resolve().parents[1]


class TestImmersiveNarrationMultiagent(unittest.TestCase):
    def test_prepare_and_merge_preserves_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_multiagent_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 10",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        audio:",
                        "          narration:",
                        "            text: \"\"",
                        "            tts_text: \"\"",
                        "            tool: \"elevenlabs\"",
                        "            output: \"assets/audio/scene10_cut01.mp3\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--scene-ids",
                    "10",
                    "--min-cuts",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            scratch = run_dir / "scratch" / "narration" / "scene10.yaml"
            text = scratch.read_text(encoding="utf-8")
            self.assertIn("target_function", text)
            self.assertIn("must_cover", text)

            scratch.write_text(
                "\n".join(
                    [
                        "scene_id: 10",
                        "cuts:",
                        "  - cut_id: 1",
                        "    target_function: \"inner_state\"",
                        "    must_cover: [\"迷い\"]",
                        "    must_avoid: [\"カメラ\"]",
                        "    done_when: [\"内面情報を1つ足す\"]",
                        "    narration_text: \"彼は、まだ一歩を決めきれずにいます。\"",
                        "    tts_text: \"かれは、まだ いっぽを きめきれずにいます。\"",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            _, manifest = load_structured_document(manifest_path)
            contract = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["contract"]
            self.assertEqual(contract["target_function"], "inner_state")
            self.assertEqual(contract["must_cover"], ["迷い"])
            self.assertEqual(contract["must_avoid"], ["カメラ"])
            self.assertEqual(manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["tts_text"], "かれは、まだ いっぽを きめきれずにいます。")
