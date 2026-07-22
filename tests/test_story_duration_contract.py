import math
import unittest

from toc.story_duration import (
    MAX_TARGET_DURATION_SECONDS,
    MIN_TARGET_DURATION_SECONDS,
    audit_duration,
    build_duration_plan,
    normalize_target_duration,
)


class StoryDurationContractTests(unittest.TestCase):
    def test_approved_duration_plans(self) -> None:
        expected = {
            300: (8, 210, 240.0),
            600: (15, 420, 480.0),
            900: (23, 630, 720.0),
            1200: (30, 840, 960.0),
        }

        for target_seconds, values in expected.items():
            with self.subTest(target_seconds=target_seconds):
                plan = build_duration_plan(target_seconds)
                self.assertEqual(
                    (
                        plan.minimum_scene_count,
                        plan.minimum_narration_seconds,
                        plan.minimum_effective_seconds,
                    ),
                    values,
                )
                self.assertEqual(
                    set(plan.to_dict()),
                    {
                        "target_seconds",
                        "minimum_scene_count",
                        "minimum_narration_seconds",
                        "minimum_effective_seconds",
                    },
                )

    def test_target_defaults_and_bounds(self) -> None:
        self.assertEqual(normalize_target_duration(None), 300)
        self.assertEqual(normalize_target_duration("600"), 600)
        self.assertEqual(normalize_target_duration(MIN_TARGET_DURATION_SECONDS), 300)
        self.assertEqual(normalize_target_duration(MAX_TARGET_DURATION_SECONDS), 1200)

        for invalid in (299, 1201, 300.5, True, "", "five minutes"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    normalize_target_duration(invalid)

    def test_duration_gate_is_lower_bound_only(self) -> None:
        target = 300

        below = audit_duration(target_seconds=target, actual_seconds=239.7, measurement_layer="audio_timeline")
        boundary = audit_duration(target_seconds=target, actual_seconds=240, measurement_layer="audio_timeline")
        over = audit_duration(target_seconds=target, actual_seconds=450, measurement_layer="audio_timeline")

        self.assertFalse(below.passed)
        self.assertTrue(boundary.passed)
        self.assertTrue(over.passed)
        self.assertTrue(math.isclose(below.ratio, 0.799, rel_tol=0, abs_tol=1e-9))
        self.assertEqual(boundary.minimum_seconds, 240.0)
        self.assertEqual(over.measurement_layer, "audio_timeline")

    def test_duration_audit_rejects_invalid_measurements(self) -> None:
        for actual in (-1, float("nan"), float("inf")):
            with self.subTest(actual=actual):
                with self.assertRaises(ValueError):
                    audit_duration(target_seconds=300, actual_seconds=actual, measurement_layer="audio_timeline")

        with self.assertRaises(ValueError):
            audit_duration(target_seconds=300, actual_seconds=240, measurement_layer="")


if __name__ == "__main__":
    unittest.main()
