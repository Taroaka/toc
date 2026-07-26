import importlib.util
import sys
import unittest
from pathlib import Path

from toc.semantic_pack_foundation import _scene_location_route_status


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_frontend_run_module():
    spec = importlib.util.spec_from_file_location(
        "cinderella_longform_frontend_run_under_test",
        REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestCinderellaLongformSemanticRegression(unittest.TestCase):
    def _build_six_hundred_second_story(self):
        module = load_frontend_run_module()
        profile = module._duration_aware_profile(
            module._story_profile(
                "シンデレラ",
                "シンデレラ",
                variant_seed="cinderella-600-semantic-regression",
            ),
            target_duration_seconds=600,
        )
        research = module._build_research(
            "シンデレラ",
            "シンデレラ",
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        profile = module._profile_from_reviewed_research(profile, research)
        story = module._build_story(
            "シンデレラ",
            REPO_ROOT / "output" / "cinderella-600-semantic-regression",
            "2099-01-01T00:00:00+09:00",
            profile,
        )
        return module, profile, story

    def test_six_hundred_second_routes_progress_without_replaying_origins(self) -> None:
        _module, profile, story = self._build_six_hundred_second_story()
        scenes = story["script"]["scenes"]

        self.assertEqual(len(scenes), 15)
        placeholder_phrases = (
            "route continuityだけ",
            "新しいroot actionを割り当てない",
            "authored owner sceneへ委ねる",
        )
        for scene in scenes:
            route = scene["location"]["sequence"]
            segments = scene["location"]["segments"]
            route_status = _scene_location_route_status(scene, int(scene["scene_id"]))
            self.assertNotEqual(route_status["status"], "invalid", route_status)
            if len(route) > 1:
                self.assertEqual(
                    [segment["location"] for segment in segments],
                    route,
                    f"scene {scene['scene_id']} must own every declared route location",
                )
            segment_text = "\n".join(
                str(segment.get(field) or "")
                for segment in segments
                for field in ("responsibility", "visible_action", "motion_brief", "motion_end_state")
            )
            self.assertFalse(
                any(phrase in segment_text for phrase in placeholder_phrases),
                f"scene {scene['scene_id']} contains a non-action route placeholder",
            )

        canonical_routes = profile["canonical_scene_location_sequences"]
        for canonical_index in range(1, 9):
            siblings = [
                scene
                for scene in scenes
                if scene["canonical_scene_index"] == canonical_index
            ]
            canonical_route = canonical_routes[canonical_index - 1]
            previous_last_position = 0
            for sibling in siblings:
                positions = [canonical_route.index(location) for location in sibling["location"]["sequence"]]
                self.assertEqual(positions, sorted(positions))
                self.assertGreaterEqual(
                    positions[0],
                    previous_last_position,
                    f"canonical scene {canonical_index} replays a completed route origin",
                )
                previous_last_position = positions[-1]

    def test_six_hundred_second_finale_has_distinct_search_and_proof_scenes(self) -> None:
        _module, _profile, story = self._build_six_hundred_second_story()
        finale = [
            scene
            for scene in story["script"]["scenes"]
            if scene["canonical_scene_index"] == 8
        ]

        self.assertGreaterEqual(len(finale), 2)
        self.assertIn("義姉たちを試す", finale[0]["segment_responsibility"])
        self.assertIn("排除", finale[0]["segment_responsibility"])
        self.assertIn("排除を退け", finale[-1]["segment_responsibility"])
        self.assertIn("足にガラスの靴が合", finale[-1]["segment_responsibility"])
        self.assertIn("公に確認", finale[-1]["segment_responsibility"])
        self.assertNotEqual(
            finale[0]["semantic_scene_responsibility_id"],
            finale[-1]["semantic_scene_responsibility_id"],
        )


if __name__ == "__main__":
    unittest.main()
