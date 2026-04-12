import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kindle.kindle_web_cdp import (  # noqa: E402
    geometry_is_clickable,
    hover_probe_points,
    numbering_mode_changed,
    page_advance_direction,
)


class TestKindleWebCdpHelpers(unittest.TestCase):
    def test_geometry_is_clickable_rejects_hidden_zero_size_button(self) -> None:
        self.assertFalse(
            geometry_is_clickable({"x": 0, "y": 0, "width": 0, "height": 0, "disabled": False})
        )
        self.assertFalse(
            geometry_is_clickable({"x": 120, "y": 400, "width": 100, "height": 44, "disabled": True})
        )
        self.assertTrue(
            geometry_is_clickable({"x": 120, "y": 400, "width": 100, "height": 44, "disabled": False})
        )

    def test_hover_probe_points_cover_both_left_and_right_edges(self) -> None:
        points = hover_probe_points(1280, 800)

        self.assertEqual(points[0]["label"], "left")
        self.assertEqual(points[0]["x"], 60)
        self.assertEqual(points[0]["y"], 400)
        self.assertEqual(points[1]["label"], "right")
        self.assertEqual(points[1]["x"], 1220)
        self.assertEqual(points[1]["y"], 400)

    def test_page_advance_direction_requires_forward_progress(self) -> None:
        self.assertEqual(page_advance_direction(10, 11), "forward")
        self.assertEqual(page_advance_direction(10, 10), "unchanged")
        self.assertEqual(page_advance_direction(10, 9), "backward")
        self.assertEqual(page_advance_direction(None, 9), "unknown")

    def test_numbering_mode_changed_detects_location_to_page_normalization(self) -> None:
        self.assertTrue(numbering_mode_changed(1, 3776, 1, 339))
        self.assertFalse(numbering_mode_changed(1, 339, 2, 339))
        self.assertFalse(numbering_mode_changed(1, 339, 1, 339))


if __name__ == "__main__":
    unittest.main()
