from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PREPARE_SCRIPT = REPO_ROOT / "scripts" / "ai" / "toc-immersive-cuts-multiagent.py"
MERGE_SCRIPT = REPO_ROOT / "scripts" / "ai" / "merge-immersive-cuts.py"


def _write_manifest(run_dir: Path, *, semantic_minimum: int | None = None) -> Path:
    scene: dict = {
        "scene_id": 10,
        "title": "legacy scene",
    }
    if semantic_minimum is not None:
        scene.update(
            {
                "scene_event": {
                    "schema_version": "scene_event_v1",
                    "event_sequence": [
                        {
                            "beat_id": f"beat_{index}",
                            "beat_function": "authored_function",
                            "must_be_seen": True,
                        }
                        for index in range(1, semantic_minimum + 1)
                    ],
                },
                "scene_cut_coverage_plan": {
                    "minimum_cut_count": semantic_minimum,
                    "selected_cut_count": semantic_minimum,
                },
                "cuts": [
                    {
                        "cut_id": index,
                        "cut_contract": {
                            "source_event_contract": {
                                "source_event_beat_ids": [f"beat_{index}"]
                            }
                        },
                    }
                    for index in range(1, semantic_minimum + 1)
                ],
            }
        )
    manifest_path = run_dir / "video_manifest.md"
    manifest_path.write_text(
        "```yaml\n"
        + yaml.safe_dump({"scenes": [scene]}, sort_keys=False, allow_unicode=True)
        + "```\n",
        encoding="utf-8",
    )
    return manifest_path


def _write_manifest_data(run_dir: Path, data: dict) -> Path:
    manifest_path = run_dir / "video_manifest.md"
    manifest_path.write_text(
        "```yaml\n"
        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        + "```\n",
        encoding="utf-8",
    )
    return manifest_path


def _write_valid_scratch(
    run_dir: Path, *, filename: str = "scene10.yaml", scene_id: int = 10
) -> Path:
    scratch_dir = run_dir / "scratch" / "cuts"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_path = scratch_dir / filename
    scratch_path.write_text(
        yaml.safe_dump(
            {
                "scene_id": scene_id,
                "cuts": [
                    {
                        "cut_id": 1,
                        "image_generation": {"prompt": "legacy raw prompt"},
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return scratch_path


def _write_scratch_data(
    run_dir: Path, data: dict, *, filename: str = "scene10.yaml"
) -> Path:
    scratch_dir = run_dir / "scratch" / "cuts"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    scratch_path = scratch_dir / filename
    scratch_path.write_text(
        yaml.safe_dump(data, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return scratch_path


def _valid_scratch_data() -> dict:
    return {
        "scene_id": 10,
        "cuts": [
            {
                "cut_id": 1,
                "image_generation": {"prompt": "legacy raw prompt"},
            }
        ],
    }


def _read_manifest_data(manifest_path: Path) -> dict:
    return yaml.safe_load(
        manifest_path.read_text(encoding="utf-8")
        .split("```yaml\n", 1)[1]
        .rsplit("\n```", 1)[0]
    )


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


class TestImmersiveCutsMultiagentLegacyIsolation(unittest.TestCase):
    def test_prepare_rejects_canonical_semantic_manifest_for_one_or_six_cuts(
        self,
    ) -> None:
        for semantic_minimum in (1, 6):
            with self.subTest(
                semantic_minimum=semantic_minimum
            ), tempfile.TemporaryDirectory(prefix="toc_cuts_canonical_prepare_") as td:
                run_dir = Path(td)
                _write_manifest(run_dir, semantic_minimum=semantic_minimum)

                result = _run(
                    PREPARE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--cut-count",
                    str(semantic_minimum),
                )

                self.assertNotEqual(result.returncode, 0)
                message = result.stdout + result.stderr
                self.assertIn("canonical semantic manifest", message.lower())
                self.assertIn("p400/create", message)
                self.assertFalse((run_dir / "scratch" / "cuts").exists())

    def test_merge_rejects_canonical_semantic_manifest(self) -> None:
        for semantic_minimum in (1, 6):
            with self.subTest(
                semantic_minimum=semantic_minimum
            ), tempfile.TemporaryDirectory(prefix="toc_cuts_canonical_merge_") as td:
                run_dir = Path(td)
                manifest_path = _write_manifest(
                    run_dir, semantic_minimum=semantic_minimum
                )
                before = manifest_path.read_bytes()
                _write_valid_scratch(run_dir)

                result = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--force",
                    "--no-backup",
                )

                self.assertNotEqual(result.returncode, 0)
                message = result.stdout + result.stderr
                self.assertIn("canonical semantic manifest", message.lower())
                self.assertIn("p400/create", message)
                self.assertEqual(manifest_path.read_bytes(), before)

    def test_each_canonical_marker_independently_blocks_prepare_and_merge(self) -> None:
        canonical_markers = {
            "scene_event": {"scene_event": {}},
            "scene_cut_coverage_plan": {"scene_cut_coverage_plan": {}},
            "cut_contract": {"cuts": [{"cut_id": 1, "cut_contract": {}}]},
            "source_event_contract": {
                "cuts": [{"cut_id": 1, "source_event_contract": {}}]
            },
            "event_context_for_cut": {
                "cuts": [{"cut_id": 1, "event_context_for_cut": {}}]
            },
            "first_frame_visual_plan": {
                "cuts": [{"cut_id": 1, "first_frame_visual_plan": {}}]
            },
            "drawable_prompt_ir": {"cuts": [{"cut_id": 1, "drawable_prompt_ir": {}}]},
        }
        for marker, scene_fragment in canonical_markers.items():
            with self.subTest(marker=marker), tempfile.TemporaryDirectory(
                prefix="toc_cuts_canonical_marker_"
            ) as td:
                run_dir = Path(td)
                scene = {"scene_id": 10, **scene_fragment}
                _write_manifest_data(run_dir, {"scenes": [scene]})

                prepared = _run(
                    PREPARE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--cut-count",
                    "1",
                )
                _write_valid_scratch(run_dir)
                merged = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--force",
                    "--no-backup",
                )

                for result in (prepared, merged):
                    self.assertNotEqual(result.returncode, 0)
                    message = result.stdout + result.stderr
                    self.assertIn(marker, message)
                    self.assertIn("p400/create", message)

    def test_both_commands_require_explicit_legacy_opt_in(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_cuts_legacy_opt_in_") as td:
            run_dir = Path(td)
            _write_manifest(run_dir)
            scratch_dir = run_dir / "scratch" / "cuts"
            scratch_dir.mkdir(parents=True)
            (scratch_dir / "scene10.yaml").write_text(
                "scene_id: 10\ncuts: []\n",
                encoding="utf-8",
            )

            prepared = _run(
                PREPARE_SCRIPT,
                "--run-dir",
                str(run_dir),
                "--cut-count",
                "1",
            )
            merged = _run(MERGE_SCRIPT, "--run-dir", str(run_dir))

            for result in (prepared, merged):
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(
                    "--legacy-fixed-cut-scaffold", result.stdout + result.stderr
                )

    def test_prepare_requires_explicit_positive_cut_count(self) -> None:
        for extra_args in ((), ("--cut-count", "0")):
            with self.subTest(extra_args=extra_args), tempfile.TemporaryDirectory(
                prefix="toc_cuts_explicit_count_"
            ) as td:
                run_dir = Path(td)
                _write_manifest(run_dir)

                result = _run(
                    PREPARE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    *extra_args,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("--cut-count", result.stdout + result.stderr)

    def test_prepare_fails_when_existing_scratch_count_disagrees_with_explicit_count(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_cuts_existing_count_") as td:
            run_dir = Path(td)
            _write_manifest(run_dir)
            scratch_path = _write_valid_scratch(run_dir)
            before = scratch_path.read_bytes()

            result = _run(
                PREPARE_SCRIPT,
                "--run-dir",
                str(run_dir),
                "--legacy-fixed-cut-scaffold",
                "--cut-count",
                "6",
            )

            self.assertNotEqual(result.returncode, 0)
            message = result.stdout + result.stderr
            self.assertIn("scene10.yaml", message)
            self.assertIn("contains 1 cuts", message)
            self.assertIn("requested --cut-count 6", message)
            self.assertEqual(scratch_path.read_bytes(), before)

    def test_legacy_explicit_one_or_six_cut_scaffolds_prepare_and_merge(self) -> None:
        for cut_count in (1, 6):
            with self.subTest(cut_count=cut_count), tempfile.TemporaryDirectory(
                prefix="toc_cuts_legacy_count_"
            ) as td:
                run_dir = Path(td)
                manifest_path = _write_manifest(run_dir)

                prepared = _run(
                    PREPARE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--cut-count",
                    str(cut_count),
                )
                self.assertEqual(prepared.returncode, 0, prepared.stderr)

                scratch_path = run_dir / "scratch" / "cuts" / "scene10.yaml"
                scratch = yaml.safe_load(scratch_path.read_text(encoding="utf-8"))
                self.assertEqual(len(scratch["cuts"]), cut_count)
                for cut in scratch["cuts"]:
                    cut["image_generation"][
                        "prompt"
                    ] = f"legacy scene 10 cut {cut['cut_id']} raw prompt"
                scratch_path.write_text(
                    yaml.safe_dump(scratch, sort_keys=False, allow_unicode=True),
                    encoding="utf-8",
                )

                merged = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--no-backup",
                )
                self.assertEqual(merged.returncode, 0, merged.stderr)
                manifest = yaml.safe_load(
                    manifest_path.read_text(encoding="utf-8")
                    .split("```yaml\n", 1)[1]
                    .rsplit("\n```", 1)[0]
                )
                self.assertEqual(len(manifest["scenes"][0]["cuts"]), cut_count)

    def test_merge_applies_cut_range_only_when_compatibility_bounds_are_explicit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_cuts_compat_bounds_") as td:
            run_dir = Path(td)
            _write_manifest(run_dir)
            scratch_dir = run_dir / "scratch" / "cuts"
            scratch_dir.mkdir(parents=True)
            (scratch_dir / "scene10.yaml").write_text(
                yaml.safe_dump(
                    {
                        "scene_id": 10,
                        "cuts": [
                            {
                                "cut_id": index,
                                "image_generation": {"prompt": f"raw prompt {index}"},
                            }
                            for index in range(1, 7)
                        ],
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            result = _run(
                MERGE_SCRIPT,
                "--run-dir",
                str(run_dir),
                "--legacy-fixed-cut-scaffold",
                "--min-cuts",
                "3",
                "--max-cuts",
                "5",
                "--no-backup",
            )

            self.assertNotEqual(result.returncode, 0)
            message = result.stdout + result.stderr
            self.assertIn("scene10.yaml", message)
            self.assertIn("6 cuts", message)
            self.assertIn("maximum 5", message)

    def test_invalid_scratch_fails_with_file_and_reason(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_cuts_invalid_scratch_") as td:
            run_dir = Path(td)
            manifest_path = _write_manifest(run_dir)
            before = manifest_path.read_bytes()
            scratch_dir = run_dir / "scratch" / "cuts"
            scratch_dir.mkdir(parents=True)
            (scratch_dir / "scene10.yaml").write_text(
                "scene_id: 10\ncuts:\n  - cut_id: 1\n    image_generation: {}\n",
                encoding="utf-8",
            )

            result = _run(
                MERGE_SCRIPT,
                "--run-dir",
                str(run_dir),
                "--legacy-fixed-cut-scaffold",
                "--no-backup",
            )

            self.assertNotEqual(result.returncode, 0)
            message = result.stdout + result.stderr
            self.assertIn("scene10.yaml", message)
            self.assertIn("prompt", message.lower())
            self.assertEqual(manifest_path.read_bytes(), before)

    def test_invalid_scalar_and_container_types_fail_closed(self) -> None:
        invalid_cases = (
            (
                "scene id float",
                {
                    "scene_id": 10.9,
                    "cuts": [{"cut_id": 1, "image_generation": {"prompt": "raw"}}],
                },
                "scene_id must be an integer",
            ),
            (
                "cut id boolean",
                {
                    "scene_id": 10,
                    "cuts": [{"cut_id": True, "image_generation": {"prompt": "raw"}}],
                },
                "cut_id must be a positive integer",
            ),
            (
                "prompt list",
                {
                    "scene_id": 10,
                    "cuts": [{"cut_id": 1, "image_generation": {"prompt": []}}],
                },
                "prompt must be a non-empty string",
            ),
            (
                "output list",
                {
                    "scene_id": 10,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {"prompt": "raw", "output": []},
                        }
                    ],
                },
                "output must be a string",
            ),
            (
                "reference mapping",
                {
                    "scene_id": 10,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {
                                "prompt": "raw",
                                "references": [{"path": "assets/reference.png"}],
                            },
                        }
                    ],
                },
                "references[0] must be a non-empty string",
            ),
        )
        for label, scratch, expected in invalid_cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="toc_cuts_invalid_types_"
            ) as td:
                run_dir = Path(td)
                manifest_path = _write_manifest(run_dir)
                before = manifest_path.read_bytes()
                scratch_dir = run_dir / "scratch" / "cuts"
                scratch_dir.mkdir(parents=True)
                (scratch_dir / "scene10.yaml").write_text(
                    yaml.safe_dump(scratch, sort_keys=False),
                    encoding="utf-8",
                )

                result = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--no-backup",
                )

                self.assertNotEqual(result.returncode, 0)
                message = result.stdout + result.stderr
                self.assertIn("scene10.yaml", message)
                self.assertIn(expected, message)
                self.assertEqual(manifest_path.read_bytes(), before)

    def test_scratch_filename_must_match_payload_scene_id(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_cuts_filename_mismatch_") as td:
            run_dir = Path(td)
            manifest_path = _write_manifest(run_dir)
            before = manifest_path.read_bytes()
            _write_valid_scratch(run_dir, filename="scene11.yaml", scene_id=10)

            result = _run(
                MERGE_SCRIPT,
                "--run-dir",
                str(run_dir),
                "--legacy-fixed-cut-scaffold",
                "--no-backup",
            )

            self.assertNotEqual(result.returncode, 0)
            message = result.stdout + result.stderr
            self.assertIn("scene11.yaml", message)
            self.assertIn("does not match payload scene_id 10", message)
            self.assertEqual(manifest_path.read_bytes(), before)

    def test_merge_rejects_recursive_canonical_provider_and_review_field_smuggling(
        self,
    ) -> None:
        smuggled_payloads = (
            (
                "canonical",
                {
                    "scene_id": 10,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {
                                "prompt": "legacy raw prompt",
                                "references": [
                                    {"nested": {"cut_contract": {"approved": True}}}
                                ],
                            },
                        }
                    ],
                },
                "cut_contract",
            ),
            (
                "provider",
                {
                    "scene_id": 10,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {
                                "prompt": "legacy raw prompt",
                                "api_prompt_payload": {
                                    "provider_request_binding": {
                                        "model": "attacker-selected"
                                    }
                                },
                            },
                        }
                    ],
                },
                "api_prompt_payload",
            ),
            (
                "review",
                {
                    "scene_id": 10,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {"prompt": "legacy raw prompt"},
                            "audio": {
                                "narration": {"p700_review": {"status": "approved"}}
                            },
                        }
                    ],
                },
                "p700_review",
            ),
        )
        for label, scratch, forbidden_key in smuggled_payloads:
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="toc_cuts_smuggled_payload_"
            ) as td:
                run_dir = Path(td)
                manifest_path = _write_manifest(run_dir)
                before = manifest_path.read_bytes()
                _write_scratch_data(run_dir, scratch)

                result = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--no-backup",
                )

                self.assertNotEqual(result.returncode, 0)
                message = result.stdout + result.stderr
                self.assertIn("forbidden", message.lower())
                self.assertIn(forbidden_key, message)
                self.assertEqual(manifest_path.read_bytes(), before)

    def test_merge_rejects_unknown_fields_at_each_legacy_schema_level(self) -> None:
        cases = (
            ("root", lambda data: data.update({"metadata": {}}), "$scratch.metadata"),
            (
                "cut",
                lambda data: data["cuts"][0].update({"duration": 4}),
                "cuts[0].duration",
            ),
            (
                "image_generation",
                lambda data: data["cuts"][0]["image_generation"].update({"seed": 7}),
                "image_generation.seed",
            ),
            (
                "audio",
                lambda data: data["cuts"][0].update({"audio": {"music": {}}}),
                "audio.music",
            ),
            (
                "narration",
                lambda data: data["cuts"][0].update(
                    {"audio": {"narration": {"voice_id": "smuggled"}}}
                ),
                "narration.voice_id",
            ),
        )
        for label, mutate, unknown_path in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="toc_cuts_unknown_field_"
            ) as td:
                run_dir = Path(td)
                manifest_path = _write_manifest(run_dir)
                before = manifest_path.read_bytes()
                scratch = _valid_scratch_data()
                mutate(scratch)
                _write_scratch_data(run_dir, scratch)

                result = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--no-backup",
                )

                self.assertNotEqual(result.returncode, 0)
                message = result.stdout + result.stderr
                self.assertIn("unknown field", message.lower())
                self.assertIn(unknown_path, message)
                self.assertEqual(manifest_path.read_bytes(), before)

    def test_merge_rejects_unsafe_image_and_narration_output_paths(self) -> None:
        cases = (
            ("absolute image", "image", "/tmp/scene10.png"),
            ("windows absolute image", "image", r"C:\\temp\\scene10.png"),
            ("unc image", "image", r"\\server\share\scene10.png"),
            ("parent image", "image", "assets/scenes/../scene10.png"),
            ("absolute narration", "narration", "/tmp/scene10.mp3"),
            ("parent narration", "narration", "assets/audio/../../scene10.mp3"),
            (
                "windows parent narration",
                "narration",
                r"assets\audio\..\scene10.mp3",
            ),
        )
        for label, output_kind, output_value in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="toc_cuts_unsafe_output_"
            ) as td:
                run_dir = Path(td)
                manifest_path = _write_manifest(run_dir)
                before = manifest_path.read_bytes()
                scratch = _valid_scratch_data()
                cut = scratch["cuts"][0]
                if output_kind == "image":
                    cut["image_generation"]["output"] = output_value
                else:
                    cut["audio"] = {
                        "narration": {"text": "narration", "output": output_value}
                    }
                _write_scratch_data(run_dir, scratch)

                result = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--no-backup",
                )

                self.assertNotEqual(result.returncode, 0)
                message = result.stdout + result.stderr
                self.assertIn("output", message)
                self.assertIn("run-relative", message)
                self.assertEqual(manifest_path.read_bytes(), before)

    def test_merge_rejects_outputs_outside_dedicated_media_roots_or_suffixes(
        self,
    ) -> None:
        cases = (
            ("image control artifact", "image", "video_manifest.md", "assets/scenes"),
            (
                "image wrong subtree",
                "image",
                "assets/audio/scene10.png",
                "assets/scenes",
            ),
            ("image wrong suffix", "image", "assets/scenes/scene10.mp3", "image file"),
            ("narration control artifact", "narration", "state.txt", "assets/audio"),
            (
                "narration wrong subtree",
                "narration",
                "assets/scenes/scene10.mp3",
                "assets/audio",
            ),
            (
                "narration wrong suffix",
                "narration",
                "assets/audio/scene10.png",
                "audio file",
            ),
        )
        for label, output_kind, output_value, expected in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="toc_cuts_output_policy_"
            ) as td:
                run_dir = Path(td)
                manifest_path = _write_manifest(run_dir)
                before = manifest_path.read_bytes()
                scratch = _valid_scratch_data()
                cut = scratch["cuts"][0]
                if output_kind == "image":
                    cut["image_generation"]["output"] = output_value
                else:
                    cut["audio"] = {
                        "narration": {"text": "narration", "output": output_value}
                    }
                _write_scratch_data(run_dir, scratch)

                result = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--no-backup",
                )

                self.assertNotEqual(result.returncode, 0)
                message = result.stdout + result.stderr
                self.assertIn("output", message)
                self.assertIn(expected, message)
                self.assertEqual(manifest_path.read_bytes(), before)

    def test_merge_rejects_duplicate_normalized_output_destinations(self) -> None:
        for output_kind in ("image", "narration"):
            with self.subTest(output_kind=output_kind), tempfile.TemporaryDirectory(
                prefix="toc_cuts_duplicate_output_"
            ) as td:
                run_dir = Path(td)
                manifest_path = _write_manifest(run_dir)
                before = manifest_path.read_bytes()
                first = {
                    "cut_id": 1,
                    "image_generation": {
                        "prompt": "legacy raw prompt 1",
                        "output": "assets/scenes/shared.png",
                    },
                    "audio": {
                        "narration": {
                            "text": "narration 1",
                            "output": "assets/audio/shared.mp3",
                        }
                    },
                }
                second = {
                    "cut_id": 2,
                    "image_generation": {
                        "prompt": "legacy raw prompt 2",
                        "output": (
                            "./assets//scenes/shared.png"
                            if output_kind == "image"
                            else "assets/scenes/unique.png"
                        ),
                    },
                    "audio": {
                        "narration": {
                            "text": "narration 2",
                            "output": (
                                "assets/audio/./shared.mp3"
                                if output_kind == "narration"
                                else "assets/audio/unique.mp3"
                            ),
                        }
                    },
                }
                _write_scratch_data(
                    run_dir,
                    {"scene_id": 10, "cuts": [first, second]},
                )

                result = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    "--no-backup",
                )

                self.assertNotEqual(result.returncode, 0)
                message = result.stdout + result.stderr
                self.assertIn("duplicate output destination", message)
                self.assertEqual(manifest_path.read_bytes(), before)

    def test_merge_rejects_case_and_unicode_equivalent_output_destinations(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_cuts_equivalent_output_") as td:
            run_dir = Path(td)
            manifest_path = _write_manifest(run_dir)
            before = manifest_path.read_bytes()
            _write_scratch_data(
                run_dir,
                {
                    "scene_id": 10,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {
                                "prompt": "legacy raw prompt 1",
                                "output": "assets/scenes/caf\u00e9.png",
                            },
                        },
                        {
                            "cut_id": 2,
                            "image_generation": {
                                "prompt": "legacy raw prompt 2",
                                "output": "assets/scenes/CAFE\u0301.png",
                            },
                        },
                    ],
                },
            )

            result = _run(
                MERGE_SCRIPT,
                "--run-dir",
                str(run_dir),
                "--legacy-fixed-cut-scaffold",
                "--no-backup",
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "duplicate output destination",
                result.stdout + result.stderr,
            )
            self.assertEqual(manifest_path.read_bytes(), before)

    def test_merge_rejects_output_path_that_traverses_symlink(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="toc_cuts_symlink_output_"
        ) as td, tempfile.TemporaryDirectory(
            prefix="toc_cuts_symlink_target_"
        ) as outside_td:
            run_dir = Path(td)
            manifest_path = _write_manifest(run_dir)
            before = manifest_path.read_bytes()
            (run_dir / "assets" / "scenes").mkdir(parents=True)
            (run_dir / "assets" / "scenes" / "escape").symlink_to(
                Path(outside_td), target_is_directory=True
            )
            scratch = _valid_scratch_data()
            scratch["cuts"][0]["image_generation"][
                "output"
            ] = "assets/scenes/escape/scene10.png"
            _write_scratch_data(run_dir, scratch)

            result = _run(
                MERGE_SCRIPT,
                "--run-dir",
                str(run_dir),
                "--legacy-fixed-cut-scaffold",
                "--no-backup",
            )

            self.assertNotEqual(result.returncode, 0)
            message = result.stdout + result.stderr
            self.assertIn("output", message)
            self.assertIn("symlink", message.lower())
            self.assertEqual(manifest_path.read_bytes(), before)

    def test_merge_normalizes_safe_output_paths_before_persistence(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_cuts_normalized_output_") as td:
            run_dir = Path(td)
            manifest_path = _write_manifest(run_dir)
            scratch = _valid_scratch_data()
            cut = scratch["cuts"][0]
            cut["image_generation"]["output"] = "./assets//scenes/scene10.png"
            cut["audio"] = {
                "narration": {
                    "text": "narration",
                    "output": "assets/audio/./scene10.mp3",
                }
            }
            _write_scratch_data(run_dir, scratch)

            result = _run(
                MERGE_SCRIPT,
                "--run-dir",
                str(run_dir),
                "--legacy-fixed-cut-scaffold",
                "--no-backup",
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            manifest = _read_manifest_data(manifest_path)
            merged_cut = manifest["scenes"][0]["cuts"][0]
            self.assertEqual(
                merged_cut["image_generation"]["output"],
                "assets/scenes/scene10.png",
            )
            self.assertEqual(
                merged_cut["audio"]["narration"]["output"],
                "assets/audio/scene10.mp3",
            )

    def test_merge_rejects_symlinked_manifest_state_and_backup_files(self) -> None:
        cases = ("manifest", "state", "backup")
        for target_kind in cases:
            with self.subTest(target_kind=target_kind), tempfile.TemporaryDirectory(
                prefix="toc_cuts_control_symlink_"
            ) as td, tempfile.TemporaryDirectory(
                prefix="toc_cuts_control_symlink_target_"
            ) as outside_td:
                run_dir = Path(td)
                outside_dir = Path(outside_td)
                external_path = outside_dir / f"{target_kind}.txt"
                extra_args = ["--no-backup"]
                if target_kind == "manifest":
                    external_path.write_text(
                        "```yaml\nscenes:\n  - scene_id: 10\n    title: legacy scene\n```\n",
                        encoding="utf-8",
                    )
                    (run_dir / "video_manifest.md").symlink_to(external_path)
                else:
                    manifest_path = _write_manifest(run_dir)
                    if target_kind == "state":
                        external_path.write_text("external state\n", encoding="utf-8")
                        (run_dir / "state.txt").symlink_to(external_path)
                    else:
                        external_path.write_text("external backup\n", encoding="utf-8")
                        (run_dir / "video_manifest.md.bak").symlink_to(external_path)
                        extra_args = []
                external_before = external_path.read_bytes()
                manifest_before = (run_dir / "video_manifest.md").read_bytes()
                _write_valid_scratch(run_dir)

                result = _run(
                    MERGE_SCRIPT,
                    "--run-dir",
                    str(run_dir),
                    "--legacy-fixed-cut-scaffold",
                    *extra_args,
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("symlink", (result.stdout + result.stderr).lower())
                self.assertEqual(external_path.read_bytes(), external_before)
                self.assertEqual(
                    (run_dir / "video_manifest.md").read_bytes(),
                    manifest_before,
                )


if __name__ == "__main__":
    unittest.main()
