import math
import unittest
from pathlib import Path

from toc.story_duration import measure_manifest_runtime


class ManifestRenderPaddingTests(unittest.TestCase):
    def _spoken_manifest(self, *, video_seconds=611, render=None):
        cut = {
            "cut_id": 1,
            "video_generation": {"duration_seconds": video_seconds},
            "audio": {
                "narration": {
                    "tool": "elevenlabs",
                    "output": "assets/audio/spoken.mp3",
                }
            },
        }
        if render is not None:
            cut["render"] = render
        return {"scenes": [{"scene_id": 1, "cuts": [cut]}]}

    def _measure(self, manifest):
        base_dir = Path("/virtual/run")
        spoken_path = base_dir / "assets/audio/spoken.mp3"
        return measure_manifest_runtime(
            manifest,
            base_dir=base_dir,
            probe=lambda path: 199.0 if path == spoken_path else None,
        )

    def test_explicit_render_allocation_counts_offset_and_tail_padding(self):
        measurement = self._measure(
            self._spoken_manifest(
                render={
                    "video_duration_seconds": 611,
                    "narration_offset_seconds": 1.5,
                }
            )
        )

        self.assertTrue(measurement.complete)
        self.assertEqual(measurement.spoken_audio_seconds, 199.0)
        self.assertEqual(measurement.audio_timeline_seconds, 611.0)
        self.assertEqual(measurement.video_timeline_seconds, 611.0)
        self.assertEqual(measurement.effective_seconds, 611.0)

    def test_allocation_must_fit_measured_audio_plus_offset(self):
        measurement = self._measure(
            self._spoken_manifest(
                render={
                    "video_duration_seconds": 200,
                    "narration_offset_seconds": 1.5,
                }
            )
        )

        self.assertFalse(measurement.complete)
        self.assertEqual(measurement.spoken_audio_seconds, 199.0)
        self.assertEqual(measurement.audio_timeline_seconds, 199.0)
        self.assertIn("scene1_cut1:render_audio_allocation", measurement.invalid_items)

    def test_invalid_render_durations_and_offsets_fail_closed(self):
        invalid_durations = (0, -1, True, "bad", math.nan, math.inf, 10**1000)
        invalid_offsets = (-0.1, True, "bad", math.nan, math.inf, 10**1000)

        for duration in invalid_durations:
            with self.subTest(duration=duration):
                measurement = self._measure(
                    self._spoken_manifest(
                        render={
                            "video_duration_seconds": duration,
                            "narration_offset_seconds": 0,
                        }
                    )
                )
                self.assertFalse(measurement.complete)
                self.assertIn("scene1_cut1:render_video_duration", measurement.invalid_items)

        for offset in invalid_offsets:
            with self.subTest(offset=offset):
                measurement = self._measure(
                    self._spoken_manifest(
                        render={
                            "video_duration_seconds": 611,
                            "narration_offset_seconds": offset,
                        }
                    )
                )
                self.assertFalse(measurement.complete)
                self.assertIn("scene1_cut1:render_narration_offset", measurement.invalid_items)

    def test_video_duration_does_not_supply_implicit_audio_padding(self):
        measurement = self._measure(self._spoken_manifest(video_seconds=611))

        self.assertTrue(measurement.complete)
        self.assertEqual(measurement.spoken_audio_seconds, 199.0)
        self.assertEqual(measurement.audio_timeline_seconds, 199.0)
        self.assertEqual(measurement.video_timeline_seconds, 611.0)
        self.assertEqual(measurement.effective_seconds, 199.0)

    def test_explicit_audio_allocation_remains_capped_by_video_timeline(self):
        measurement = self._measure(
            self._spoken_manifest(
                video_seconds=300,
                render={
                    "video_duration_seconds": 611,
                    "narration_offset_seconds": 0,
                },
            )
        )

        self.assertTrue(measurement.complete)
        self.assertEqual(measurement.audio_timeline_seconds, 611.0)
        self.assertEqual(measurement.video_timeline_seconds, 300.0)
        self.assertEqual(measurement.effective_seconds, 300.0)

    def test_cinematic_direction_can_author_silence_without_human_confirmation(self):
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "video_generation": {"duration_seconds": 4},
                            "audio": {
                                "narration": {
                                    "tool": "silent",
                                    "authoring_status": "silent",
                                    "silence_contract": {
                                        "intentional": True,
                                        "source": "cinematic_direction_v1",
                                        "reason": "Hold the image without narration.",
                                        "confirmed_by_human": False,
                                    },
                                }
                            },
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

        self.assertTrue(measurement.complete)
        self.assertEqual(measurement.intentional_silence_seconds, 4.0)
        self.assertEqual(measurement.audio_timeline_seconds, 4.0)
        self.assertEqual(measurement.missing_items, ())
        self.assertEqual(measurement.invalid_items, ())

    def test_cinematic_silence_still_requires_a_reason(self):
        manifest = {
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "video_generation": {"duration_seconds": 4},
                            "audio": {
                                "narration": {
                                    "tool": "silent",
                                    "authoring_status": "silent",
                                    "silence_contract": {
                                        "intentional": True,
                                        "source": "cinematic_direction_v1",
                                        "confirmed_by_human": False,
                                    },
                                }
                            },
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
        self.assertIn("scene1_cut1:silence_contract", measurement.invalid_items)


if __name__ == "__main__":
    unittest.main()
