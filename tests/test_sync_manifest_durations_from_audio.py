import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "sync-manifest-durations-from-audio.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNC_MODULE = _load_module(SCRIPT_PATH, "sync_manifest_durations_from_audio")


def _write_manifest(path: Path, manifest: dict) -> None:
    yaml_text = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
    path.write_text(f"# Manifest\n\n```yaml\n{yaml_text}```\n", encoding="utf-8")


def _read_manifest(path: Path) -> dict:
    return yaml.safe_load(SYNC_MODULE.extract_yaml_block(path.read_text(encoding="utf-8")))


def _run_sync(manifest_path: Path, *, durations: dict[Path, float]) -> None:
    argv = [
        str(SCRIPT_PATH),
        "--manifest",
        str(manifest_path),
        "--default-padding-seconds",
        "0",
        "--sub-padding-seconds",
        "0",
        "--linger-padding-seconds",
        "0",
        "--no-backup",
    ]
    with (
        patch.object(sys, "argv", argv),
        patch.object(SYNC_MODULE, "_ffprobe_duration_seconds", side_effect=lambda path: durations[path]),
    ):
        SYNC_MODULE.main()


class SyncManifestDurationsFromAudioTests(unittest.TestCase):
    def test_ffprobe_and_duration_policy_helpers(self) -> None:
        self.assertIsNone(SYNC_MODULE._as_opt_str(None))
        self.assertIsNone(SYNC_MODULE._resolve_path(Path("/run"), None))
        self.assertEqual(SYNC_MODULE._infer_cut_role(cut={}, cut_index=0, cut_count=1), "main")
        completed = SimpleNamespace(stdout="7.25\n", stderr="")
        with patch.object(SYNC_MODULE.subprocess, "run", return_value=completed) as run:
            self.assertEqual(SYNC_MODULE._ffprobe_duration_seconds(Path("audio.wav")), 7.25)
        self.assertIn("ffprobe", run.call_args.args[0])

        args = SimpleNamespace(
            default_padding_seconds=1.0,
            sub_padding_seconds=0.5,
            linger_padding_seconds=1.5,
        )
        self.assertEqual(SYNC_MODULE._padding_preset_seconds(preset="linger", args=args), 1.5)
        self.assertEqual(SYNC_MODULE._padding_preset_seconds(preset="sub", args=args), 0.5)
        self.assertEqual(SYNC_MODULE._padding_preset_seconds(preset="default", args=args), 1.0)
        self.assertEqual(
            SYNC_MODULE._resolve_padding_seconds(
                container={"duration_padding_seconds": 2.0},
                role="main",
                args=args,
            ),
            2.0,
        )
        self.assertEqual(
            SYNC_MODULE._resolve_padding_seconds(
                container={"duration_padding_preset": "linger"},
                role="main",
                args=args,
            ),
            1.5,
        )
        self.assertEqual(SYNC_MODULE._round_duration(2.6, mode="round"), 3)
        self.assertEqual(SYNC_MODULE._round_duration(2.6, mode="floor"), 2)

    def test_confirmed_intentional_silence_is_included_in_derived_runtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_duration_") as td:
            run_dir = Path(td)
            audio_path = run_dir / "assets/audio/spoken.wav"
            audio_path.parent.mkdir(parents=True)
            audio_path.write_bytes(b"fake")
            manifest_path = run_dir / "video_manifest.md"
            _write_manifest(
                manifest_path,
                {
                    "video_metadata": {"duration_seconds": 999},
                    "scenes": [
                        {
                            "scene_id": 1,
                            "cuts": [
                                {
                                    "cut_id": 1,
                                    "video_generation": {"duration_seconds": 2},
                                    "audio": {
                                        "narration": {
                                            "tool": "elevenlabs",
                                            "output": "assets/audio/spoken.wav",
                                        }
                                    },
                                },
                                {
                                    "cut_id": 2,
                                    "video_generation": {"duration_seconds": 4},
                                    "audio": {
                                        "narration": {
                                            "tool": "silent",
                                            "silence_contract": {
                                                "intentional": True,
                                                "confirmed_by_human": True,
                                                "kind": "reaction_hold",
                                                "reason": "映像だけで見せる",
                                            },
                                        }
                                    },
                                },
                            ],
                        }
                    ],
                },
            )

            _run_sync(manifest_path, durations={audio_path: 4.0})

            manifest = _read_manifest(manifest_path)
            self.assertEqual(manifest["scenes"][0]["cuts"][0]["video_generation"]["duration_seconds"], 5)
            self.assertEqual(manifest["scenes"][0]["cuts"][1]["video_generation"]["duration_seconds"], 4)
            self.assertEqual(manifest["scenes"][0]["timestamp"], "00:00-00:09")
            self.assertEqual(manifest["video_metadata"]["duration_seconds"], 8)

    def test_render_units_replace_cut_video_timeline_without_double_counting(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_duration_") as td:
            run_dir = Path(td)
            first_audio = run_dir / "assets/audio/first.wav"
            second_audio = run_dir / "assets/audio/second.wav"
            first_audio.parent.mkdir(parents=True)
            first_audio.write_bytes(b"fake")
            second_audio.write_bytes(b"fake")
            manifest_path = run_dir / "video_manifest.md"
            _write_manifest(
                manifest_path,
                {
                    "video_metadata": {"duration_seconds": 999},
                    "scenes": [
                        {
                            "scene_id": 2,
                            "cuts": [
                                {
                                    "cut_id": 1,
                                    "video_generation": {"duration_seconds": 6},
                                    "audio": {
                                        "narration": {
                                            "tool": "elevenlabs",
                                            "output": "assets/audio/first.wav",
                                        }
                                    },
                                },
                                {
                                    "cut_id": 2,
                                    "cut_role": "sub",
                                    "video_generation": {"duration_seconds": 6},
                                    "audio": {
                                        "narration": {
                                            "tool": "elevenlabs",
                                            "output": "assets/audio/second.wav",
                                        }
                                    },
                                },
                            ],
                            "render_units": [
                                {
                                    "unit_id": 1,
                                    "source_cut_ids": [1, 2],
                                    "video_generation": {"duration_seconds": 8},
                                }
                            ],
                        }
                    ],
                },
            )

            _run_sync(manifest_path, durations={first_audio: 5.0, second_audio: 5.0})

            manifest = _read_manifest(manifest_path)
            self.assertEqual(manifest["scenes"][0]["timestamp"], "00:00-00:08")
            self.assertEqual(manifest["scenes"][0]["render_units"][0]["video_generation"]["duration_seconds"], 8)
            self.assertEqual(manifest["video_metadata"]["duration_seconds"], 8)

    def test_bare_silent_cut_is_not_accepted_as_measured_runtime(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_duration_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            _write_manifest(
                manifest_path,
                {
                    "video_metadata": {"duration_seconds": 999},
                    "scenes": [
                        {
                            "scene_id": 3,
                            "cuts": [
                                {
                                    "cut_id": 1,
                                    "video_generation": {"duration_seconds": 4},
                                    "audio": {"narration": {"tool": "silent"}},
                                }
                            ],
                        }
                    ],
                },
            )

            with self.assertRaisesRegex(SystemExit, "complete silence_contract"):
                _run_sync(manifest_path, durations={})

            self.assertEqual(_read_manifest(manifest_path)["video_metadata"]["duration_seconds"], 999)


if __name__ == "__main__":
    unittest.main()
