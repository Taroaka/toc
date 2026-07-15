import unittest
from pathlib import Path

from toc.story_duration import measure_manifest_runtime


class ManifestRuntimeMeasurementTests(unittest.TestCase):
    def test_non_renderable_reference_scenes_are_excluded(self) -> None:
        base_dir = Path("/virtual/run")
        spoken_path = base_dir / "assets/audio/scene1.mp3"
        manifest = {
            "scenes": [
                {
                    "scene_id": 0,
                    "kind": "character_reference",
                    "image_generation": {"output": "assets/characters/hero.png"},
                },
                {
                    "scene_id": 1,
                    "video_generation": {"duration_seconds": 5},
                    "audio": {
                        "narration": {
                            "tool": "elevenlabs",
                            "output": "assets/audio/scene1.mp3",
                        }
                    },
                },
            ]
        }

        measurement = measure_manifest_runtime(
            manifest,
            base_dir=base_dir,
            probe=lambda path: 5.0 if path == spoken_path else None,
        )

        self.assertTrue(measurement.complete)
        self.assertEqual(measurement.audio_timeline_seconds, 5.0)
        self.assertEqual(measurement.video_timeline_seconds, 5.0)
        self.assertEqual(measurement.missing_items, ())

    def test_scene_with_only_deleted_or_reference_cuts_is_excluded(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {"cut_id": 1, "cut_status": "deleted"},
                        {"cut_id": 2, "kind": "location_reference"},
                    ],
                },
                {"scene_id": 2, "scene_kind": "character_reference"},
            ]
        }

        measurement = measure_manifest_runtime(
            manifest,
            base_dir=Path("/virtual/run"),
            probe=lambda _path: None,
        )

        self.assertFalse(measurement.complete)
        self.assertEqual(measurement.audio_timeline_seconds, 0.0)
        self.assertEqual(measurement.video_timeline_seconds, 0.0)
        self.assertEqual(
            measurement.missing_items,
            ("manifest:audio_timeline", "manifest:video_timeline"),
        )

    def test_spoken_audio_and_confirmed_intentional_silence_share_the_audio_timeline(self) -> None:
        base_dir = Path("/virtual/run")
        spoken_path = base_dir / "assets/audio/scene1_cut1.mp3"
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "video_generation": {"duration_seconds": 8},
                            "audio": {
                                "narration": {
                                    "tool": "elevenlabs",
                                    "output": "assets/audio/scene1_cut1.mp3",
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
                                        "reason": "表情を声で説明しない",
                                    },
                                }
                            },
                        },
                    ],
                }
            ]
        }

        measurement = measure_manifest_runtime(
            manifest,
            base_dir=base_dir,
            probe=lambda path: 6.25 if path == spoken_path else None,
        )

        self.assertTrue(measurement.complete)
        self.assertEqual(measurement.spoken_audio_seconds, 6.25)
        self.assertEqual(measurement.intentional_silence_seconds, 4.0)
        self.assertEqual(measurement.audio_timeline_seconds, 10.25)
        self.assertEqual(measurement.video_timeline_seconds, 12.0)
        self.assertEqual(measurement.effective_seconds, 10.25)
        self.assertEqual(measurement.missing_items, ())
        self.assertEqual(measurement.invalid_items, ())

    def test_bare_silent_tool_is_incomplete(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "video_generation": {"duration_seconds": 4},
                            "audio": {"narration": {"tool": "silent"}},
                        }
                    ],
                }
            ]
        }

        measurement = measure_manifest_runtime(
            manifest,
            base_dir=Path("/virtual/run"),
            probe=lambda _path: None,
        )

        self.assertFalse(measurement.complete)
        self.assertEqual(measurement.intentional_silence_seconds, 0.0)
        self.assertEqual(measurement.audio_timeline_seconds, 0.0)
        self.assertEqual(measurement.video_timeline_seconds, 4.0)
        self.assertEqual(measurement.effective_seconds, 0.0)
        self.assertIn("scene1_cut1:silence_contract", measurement.invalid_items)

    def test_render_units_replace_cut_video_durations_without_double_counting(self) -> None:
        base_dir = Path("/virtual/run")
        durations = {
            base_dir / "assets/audio/scene2_cut1.mp3": 5.0,
            base_dir / "assets/audio/scene2_cut2.mp3": 5.0,
        }
        manifest = {
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
                                    "output": "assets/audio/scene2_cut1.mp3",
                                }
                            },
                        },
                        {
                            "cut_id": 2,
                            "video_generation": {"duration_seconds": 6},
                            "audio": {
                                "narration": {
                                    "tool": "elevenlabs",
                                    "output": "assets/audio/scene2_cut2.mp3",
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
            ]
        }

        measurement = measure_manifest_runtime(
            manifest,
            base_dir=base_dir,
            probe=durations.get,
        )

        self.assertTrue(measurement.complete)
        self.assertEqual(measurement.audio_timeline_seconds, 10.0)
        self.assertEqual(measurement.video_timeline_seconds, 8.0)
        self.assertEqual(measurement.effective_seconds, 8.0)
        self.assertEqual(measurement.video_timeline_source, "render_units")

    def test_missing_and_invalid_measurements_are_reported_without_io(self) -> None:
        manifest = {
            "scenes": [
                {
                    "scene_id": 3,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "audio": {"narration": {"tool": "elevenlabs"}},
                        },
                        {
                            "cut_id": 2,
                            "audio": {
                                "narration": {
                                    "tool": "elevenlabs",
                                    "output": "assets/audio/broken.mp3",
                                }
                            },
                        },
                    ],
                    "render_units": [
                        {
                            "unit_id": 1,
                            "source_cut_ids": [1, 2],
                            "video_generation": {"duration_seconds": "not-a-number"},
                        }
                    ],
                }
            ]
        }

        measurement = measure_manifest_runtime(
            manifest,
            base_dir=Path("/virtual/run"),
            probe=lambda _path: None,
        )

        self.assertFalse(measurement.complete)
        self.assertIn("scene3_cut1:audio_output", measurement.missing_items)
        self.assertIn("scene3_cut2:audio_duration", measurement.invalid_items)
        self.assertIn("scene3_unit1:video_duration", measurement.invalid_items)


if __name__ == "__main__":
    unittest.main()
