import importlib.util
import unittest
from pathlib import Path
import sys


def _load_generate_assets_module(repo_root: Path):
    script = repo_root / "scripts" / "generate-assets-from-manifest.py"
    spec = importlib.util.spec_from_file_location("generate_assets_from_manifest", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


class TestManifestParsing(unittest.TestCase):
    def test_parse_manifest_supports_references_and_first_last(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
video_metadata:
  topic: "t"
  aspect_ratio: "16:9"
  resolution: "1280x720"

scenes:
  - scene_id: 1
    timestamp: "00:00-00:08"
    image_generation:
      tool: "google_nanobanana_pro"
      prompt: "p"
      output: "assets/scenes/scene1.png"
      references: ["assets/characters/c.png", "assets/styles/s.png"]
      aspect_ratio: "16:9"
      image_size: "2K"
    video_generation:
      tool: "google_veo_3_1"
      first_frame: "assets/scenes/scene1.png"
      last_frame: "assets/scenes/scene2.png"
      motion_prompt: "m"
      output: "assets/scenes/scene1_to_2.mp4"
    audio:
      narration:
        tool: "elevenlabs"
        text: "n"
        output: "assets/audio/n.mp3"
        normalize_to_scene_duration: false
```
"""

        yaml_text = mod.extract_yaml_block(md)
        metadata, scenes = mod.parse_manifest_yaml(yaml_text)

        self.assertEqual(metadata["topic"], "t")
        self.assertEqual(scenes[0].image_references, ["assets/characters/c.png", "assets/styles/s.png"])
        self.assertEqual(scenes[0].video_first_frame, "assets/scenes/scene1.png")
        self.assertEqual(scenes[0].video_last_frame, "assets/scenes/scene2.png")
        self.assertIs(scenes[0].narration_normalize_to_scene_duration, False)

    def test_parse_manifest_supports_cuts(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
scenes:
  - scene_id: 10
    timestamp: "00:00-00:24"
    cuts:
      - cut_id: 1
        image_generation:
          tool: "google_nanobanana_pro"
          character_ids: []
          object_ids: []
          prompt: "p1"
          output: "assets/scenes/scene10_1.png"
          references: []
        video_generation:
          tool: "google_veo_3_1"
          first_frame: "assets/scenes/scene10_1.png"
          last_frame: "assets/scenes/scene10_2.png"
          motion_prompt: "m1"
          output: "assets/scenes/scene10_1_to_2.mp4"
      - cut_id: 2
        image_generation:
          tool: "google_nanobanana_pro"
          character_ids: []
          object_ids: []
          prompt: "p2"
          output: "assets/scenes/scene10_2.png"
          references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, scenes = mod.parse_manifest_yaml(yaml_text)

        self.assertEqual([s.scene_id for s in scenes], [1001, 1002])
        self.assertEqual(scenes[0].timestamp, "00:00-00:24")
        self.assertEqual(scenes[0].image_output, "assets/scenes/scene10_1.png")
        self.assertEqual(scenes[0].video_output, "assets/scenes/scene10_1_to_2.mp4")

    def test_parse_manifest_supports_cut_duration_seconds_override(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
scenes:
  - scene_id: 10
    timestamp: "00:00-00:24"
    cuts:
      - cut_id: 1
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 12
          input_image: "assets/scenes/scene10_1.png"
          motion_prompt: "m1"
          output: "assets/scenes/scene10_1.mp4"
      - cut_id: 2
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 7
          input_image: "assets/scenes/scene10_2.png"
          motion_prompt: "m2"
          output: "assets/scenes/scene10_2.mp4"
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, scenes = mod.parse_manifest_yaml(yaml_text)

        self.assertEqual([s.scene_id for s in scenes], [1001, 1002])
        self.assertEqual([s.duration_seconds for s in scenes], [12, 7])

    def test_parse_manifest_supports_character_reference_id_selectors(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
scenes:
  - scene_id: 0
    reference_id: protagonist_front_ref
    kind: character_reference
    image_generation:
      tool: "google_nanobanana_pro"
      prompt: "character ref"
      output: "assets/characters/protagonist_front.png"
      references: []
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_pro"
      prompt: "story"
      output: "assets/scenes/scene10.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, scenes = mod.parse_manifest_yaml(yaml_text)

        self.assertEqual(scenes[0].scene_id, 0)
        self.assertEqual(scenes[0].manifest_scene_id, 0)
        self.assertEqual(scenes[0].reference_id, "protagonist_front_ref")
        self.assertEqual(scenes[0].kind, "character_reference")
        self.assertTrue(mod._scene_matches_filter(scenes[0], {"protagonist_front_ref"}))
        self.assertTrue(mod._scene_matches_filter(scenes[0], {"0"}))
        self.assertTrue(mod._scene_matches_filter(scenes[1], {"10"}))
        self.assertFalse(mod._scene_matches_filter(scenes[1], {"protagonist_front_ref"}))

    def test_parse_manifest_supports_reference_variants_and_scene_variant_selectors(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  character_bible:
    - character_id: "hero"
      fixed_prompts: ["hero base"]
      reference_variants:
        - variant_id: "hero_day"
          reference_images:
            - "assets/characters/hero_day_front.png"
            - "assets/characters/hero_day_side.png"
          fixed_prompts:
            - "day outfit"
    - character_id: "villain"
      reference_images: ["assets/characters/villain.png"]
      fixed_prompts: ["villain base"]
  object_bible:
    - object_id: "amulet"
      fixed_prompts: ["amulet base"]
      reference_variants:
        - variant_id: "amulet_glowing"
          reference_images: ["assets/objects/amulet_glowing.png"]
          fixed_prompts: ["amulet emits blue light"]

scenes:
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["hero", "villain"]
      character_variant_ids: ["hero_day"]
      object_ids: ["amulet"]
      object_variant_ids: ["amulet_glowing"]
      prompt: "story"
      output: "assets/scenes/scene10.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)

        self.assertEqual(guides.character_bible[0].reference_variants[0].variant_id, "hero_day")
        self.assertEqual(
            guides.character_bible[0].reference_variants[0].reference_images,
            ["assets/characters/hero_day_front.png", "assets/characters/hero_day_side.png"],
        )
        self.assertEqual(guides.object_bible[0].reference_variants[0].variant_id, "amulet_glowing")
        self.assertEqual(scenes[0].image_character_variant_ids, ["hero_day"])
        self.assertEqual(scenes[0].image_object_variant_ids, ["amulet_glowing"])


if __name__ == "__main__":
    unittest.main()
