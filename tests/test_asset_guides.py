import importlib.util
import sys
import unittest
from pathlib import Path


def _load_generate_assets_module(repo_root: Path):
    script = repo_root / "scripts" / "generate-assets-from-manifest.py"
    spec = importlib.util.spec_from_file_location("generate_assets_from_manifest", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


class TestAssetGuides(unittest.TestCase):
    def test_derive_character_view_paths_supports_plain_and_front_suffix(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        p_plain = Path("assets/characters/hero.png")
        self.assertEqual(str(mod._derive_character_view_path(p_plain, "front")), "assets/characters/hero.png")
        self.assertEqual(str(mod._derive_character_view_path(p_plain, "side")), "assets/characters/hero_side.png")
        self.assertEqual(str(mod._derive_character_view_path(p_plain, "back")), "assets/characters/hero_back.png")

        p_front = Path("assets/characters/hero_front.png")
        self.assertEqual(str(mod._derive_character_view_path(p_front, "front")), "assets/characters/hero_front.png")
        self.assertEqual(str(mod._derive_character_view_path(p_front, "side")), "assets/characters/hero_side.png")
        self.assertEqual(str(mod._derive_character_view_path(p_front, "back")), "assets/characters/hero_back.png")

        strip = mod._derive_character_refstrip_path(p_front, "_refstrip")
        self.assertEqual(str(strip), "assets/characters/hero_refstrip.png")

    def test_parse_and_apply_asset_guides_merges_refs_and_injects_prompt(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
video_metadata:
  topic: "t"
  aspect_ratio: "16:9"
  resolution: "1280x720"

assets:
  character_bible:
    - character_id: "hero"
      reference_images:
        - "assets/characters/hero.png"
      fixed_prompts:
        - "hero matches reference exactly"
    - character_id: "villain"
      reference_images:
        - "assets/characters/villain.png"
      fixed_prompts:
        - "villain matches reference exactly"
  style_guide:
    visual_style: "photorealistic, cinematic, practical effects"
    forbidden:
      - "animated"
      - "anime"
    reference_images:
      - "assets/styles/style.png"

scenes:
  - scene_id: 0
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["hero"]
      prompt: |
        [GLOBAL / INVARIANTS]
        base global

        [SCENE]
        base scene
      output: "assets/characters/hero.png"
      references: []
  - scene_id: 1
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["hero", "villain"]
      prompt: |
        [GLOBAL / INVARIANTS]
        base global

        [CHARACTERS]
        base characters

        [SCENE]
        base scene

        [AVOID]
        base avoid
      output: "assets/scenes/scene1.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        metadata, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)

        self.assertEqual(metadata["topic"], "t")
        self.assertEqual(len(guides.character_bible), 2)
        self.assertIsNotNone(guides.style_guide)

        for scene in scenes:
            mod.apply_asset_guides_to_scene(scene=scene, guides=guides, character_refs_mode="scene")

        scene0 = scenes[0]
        scene1 = scenes[1]

        # Scene 0 generates the character ref; avoid self-reference.
        self.assertNotIn("assets/characters/hero.png", scene0.image_references)

        # Scene 1 should inherit global refs (style + character).
        self.assertIn("assets/characters/hero.png", scene1.image_references)
        self.assertIn("assets/characters/villain.png", scene1.image_references)
        self.assertIn("assets/styles/style.png", scene1.image_references)

        # Prompt: style guide should be injected under GLOBAL, character fixed prompt under CHARACTERS, forbidden under AVOID.
        lines = scene1.image_prompt.splitlines()
        self.assertIn("photorealistic, cinematic, practical effects", lines)
        self.assertIn("hero matches reference exactly", lines)
        self.assertIn("villain matches reference exactly", lines)
        self.assertIn("animated", lines)
        self.assertIn("anime", lines)

        idx_global = lines.index("[GLOBAL / INVARIANTS]")
        self.assertEqual(lines[idx_global + 1], "photorealistic, cinematic, practical effects")

        idx_char = lines.index("[CHARACTERS]")
        self.assertEqual(lines[idx_char + 1], "hero matches reference exactly")

        idx_avoid = lines.index("[AVOID]")
        self.assertEqual(lines[idx_avoid + 1], "animated")

    def test_require_character_ids_fails_when_missing(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  character_bible:
    - character_id: "hero"
      reference_images: ["assets/characters/hero.png"]
      fixed_prompts: ["hero matches reference exactly"]

scenes:
  - scene_id: 1
    image_generation:
      tool: "google_nanobanana_pro"
      # character_ids intentionally missing
      prompt: |
        [GLOBAL / INVARIANTS]
        base
      output: "assets/scenes/scene1.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)
        mod.apply_asset_guides_to_scene(scene=scenes[0], guides=guides, character_refs_mode="scene")

        with self.assertRaises(SystemExit) as ctx:
            mod.validate_scene_character_ids(
                scenes=scenes, require=True, mode="scene", scene_filter=None
            )
        self.assertIn("missing image_generation.character_ids", str(ctx.exception))

    def test_apply_asset_guides_uses_selected_character_variant_refs(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  character_bible:
    - character_id: "hero"
      reference_images: ["assets/characters/hero_default.png"]
      fixed_prompts: ["hero base"]
      reference_variants:
        - variant_id: "hero_day"
          reference_images:
            - "assets/characters/hero_day_front.png"
            - "assets/characters/hero_day_side.png"
          fixed_prompts:
            - "day costume"
        - variant_id: "hero_night"
          reference_images: ["assets/characters/hero_night_front.png"]
          fixed_prompts:
            - "night costume"

scenes:
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["hero"]
      character_variant_ids: ["hero_night"]
      object_ids: []
      prompt: |
        [CHARACTERS]
        base characters

        [SCENE]
        story
      output: "assets/scenes/scene10.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)

        mod.validate_scene_reference_variant_ids(scenes=scenes, guides=guides, require=True, scene_filter=None)
        mod.apply_asset_guides_to_scene(scene=scenes[0], guides=guides, character_refs_mode="scene")

        self.assertEqual(scenes[0].image_references, ["assets/characters/hero_night_front.png"])
        self.assertIn("hero base", scenes[0].image_prompt)
        self.assertIn("night costume", scenes[0].image_prompt)
        self.assertNotIn("day costume", scenes[0].image_prompt)

    def test_unknown_character_variant_id_fails_validation(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  character_bible:
    - character_id: "hero"
      reference_variants:
        - variant_id: "hero_day"
          reference_images: ["assets/characters/hero_day_front.png"]

scenes:
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["hero"]
      character_variant_ids: ["hero_missing"]
      object_ids: []
      prompt: "story"
      output: "assets/scenes/scene10.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)

        with self.assertRaises(SystemExit) as ctx:
            mod.validate_scene_reference_variant_ids(scenes=scenes, guides=guides, require=True, scene_filter=None)
        self.assertIn("unknown character_variant_ids", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
