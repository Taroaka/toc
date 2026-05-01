import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "migrate-audio-first-slot-contract.py"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import parse_state_file


class TestMigrateAudioFirstSlotContract(unittest.TestCase):
    def test_migration_remaps_slots_and_grounding_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_audiofirst_migrate_") as td:
            run_dir = Path(td) / "output" / "momotaro_20990101_0000"
            grounding_dir = run_dir / "logs" / "grounding"
            grounding_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "# Manifest",
                        "",
                        "```yaml",
                        "video_metadata:",
                        '  topic: "桃太郎"',
                        "scenes: []",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "topic=桃太郎",
                        "slot.p830.status=done",
                        "stage.image_prompt.grounding.status=ready",
                        "stage.image_prompt.grounding.report=logs/grounding/image_prompt.json",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (grounding_dir / "image_prompt.json").write_text('{"status":"ready"}\n', encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--run-dir", str(run_dir)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            self.assertTrue((grounding_dir / "scene_implementation.json").exists())
            self.assertFalse((grounding_dir / "image_prompt.json").exists())
            manifest = (run_dir / "video_manifest.md").read_text(encoding="utf-8")
            self.assertIn("manifest_phase: production", manifest)

            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("slot.p540.status"), "done")
            self.assertEqual(state.get("stage.scene_implementation.grounding.status"), "ready")
            self.assertEqual(
                state.get("stage.scene_implementation.grounding.report"),
                "logs/grounding/scene_implementation.json",
            )
            self.assertEqual(state.get("slot.p450.status"), "done")
            self.assertTrue((run_dir / "p000_index.md").exists())

    def test_migration_preserves_existing_new_slot_values_and_existing_grounding(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_audiofirst_migrate_preserve_") as td:
            run_dir = Path(td) / "output" / "kaguya_20990101_0000"
            grounding_dir = run_dir / "logs" / "grounding"
            grounding_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "video_manifest.md").write_text(
                "\n".join(
                    [
                        "# Manifest",
                        "",
                        "```yaml",
                        "manifest_phase: production",
                        "video_metadata:",
                        '  topic: "かぐや姫"',
                        "scenes: []",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "state.txt").write_text(
                "\n".join(
                    [
                        "topic=かぐや姫",
                        "slot.p830.status=done",
                        "slot.p540.status=failed",
                        "stage.image_prompt.grounding.status=ready",
                        "stage.scene_implementation.grounding.status=missing_inputs",
                        "---",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            (grounding_dir / "image_prompt.json").write_text('{"status":"ready","source":"old"}\n', encoding="utf-8")
            (grounding_dir / "scene_implementation.json").write_text(
                '{"status":"missing_inputs","source":"new"}\n',
                encoding="utf-8",
            )

            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--run-dir", str(run_dir)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, msg=result.stderr)
            state = parse_state_file(run_dir / "state.txt")
            self.assertEqual(state.get("slot.p540.status"), "failed")
            self.assertEqual(state.get("stage.scene_implementation.grounding.status"), "missing_inputs")
            self.assertTrue((grounding_dir / "image_prompt.json").exists())
            self.assertTrue((grounding_dir / "scene_implementation.json").exists())


if __name__ == "__main__":
    unittest.main()
