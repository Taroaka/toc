import unittest

from toc.immersive_manifest import (
    default_story_scene_start,
    manifest_scene_selector_tokens,
    selector_matches,
    story_scene_ids,
)


class TestImmersiveManifestIds(unittest.TestCase):
    def test_story_scene_ids_ignore_character_reference_and_default_to_10_step(self) -> None:
        scenes = [
            {
                "scene_id": 0,
                "reference_id": "protagonist_front_ref",
                "kind": "character_reference",
                "image_generation": {"output": "assets/characters/protagonist_front.png"},
            },
            {"scene_id": 10, "image_generation": {"output": "assets/scenes/scene10.png"}},
            {"scene_id": 20, "image_generation": {"output": "assets/scenes/scene20.png"}},
        ]

        self.assertEqual(story_scene_ids(scenes), [10, 20])
        self.assertEqual(default_story_scene_start(scenes), 10)

    def test_story_scene_start_stays_compatible_with_legacy_sequential_ids(self) -> None:
        scenes = [
            {"scene_id": 1, "image_generation": {"output": "assets/scenes/scene01.png"}},
            {"scene_id": 2, "image_generation": {"output": "assets/scenes/scene02.png"}},
        ]

        self.assertEqual(story_scene_ids(scenes), [1, 2])
        self.assertEqual(default_story_scene_start(scenes), 1)

    def test_selector_tokens_include_numeric_and_reference_ids(self) -> None:
        scene = {
            "scene_id": 0,
            "reference_id": "protagonist_front_ref",
            "kind": "character_reference",
            "image_generation": {"output": "assets/characters/protagonist_front.png"},
        }

        tokens = manifest_scene_selector_tokens(scene)

        self.assertEqual(tokens, {"0", "protagonist_front_ref"})
        self.assertTrue(selector_matches(tokens, {"protagonist_front_ref"}))
        self.assertTrue(selector_matches(tokens, {"0"}))
        self.assertFalse(selector_matches(tokens, {"10"}))


if __name__ == "__main__":
    unittest.main()
