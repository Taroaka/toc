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
      tool: "google_nanobanana_2"
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
        tts_text: "えぬ"
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
        self.assertEqual(scenes[0].narration_tts_text, "えぬ")
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
          tool: "google_nanobanana_2"
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
          tool: "google_nanobanana_2"
          character_ids: []
          object_ids: []
          prompt: "p2"
          output: "assets/scenes/scene10_2.png"
          references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, scenes = mod.parse_manifest_yaml(yaml_text)

        self.assertEqual([s.scene_id for s in scenes], ["scene10_cut1", "scene10_cut2"])
        self.assertEqual([s.selector for s in scenes], ["scene10_cut1", "scene10_cut2"])
        self.assertEqual([s.manifest_scene_id for s in scenes], ["10", "10"])
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

        self.assertEqual([s.scene_id for s in scenes], ["scene10_cut1", "scene10_cut2"])
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
      tool: "google_nanobanana_2"
      prompt: "character ref"
      output: "assets/characters/protagonist_front.png"
      references: []
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_2"
      prompt: "story"
      output: "assets/scenes/scene10.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, scenes = mod.parse_manifest_yaml(yaml_text)

        self.assertEqual(scenes[0].scene_id, "0")
        self.assertEqual(scenes[0].manifest_scene_id, "0")
        self.assertEqual(scenes[0].selector, "scene0")
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
      tool: "google_nanobanana_2"
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

    def test_parse_manifest_supports_character_physical_scale_and_relative_rules(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  character_bible:
    - character_id: "hero"
      reference_images: ["assets/characters/hero.png"]
      physical_scale:
        height_cm: 178
        silhouette_notes:
          - "adult natural build"
      relative_scale_rules:
        - "hero keeps the same body scale across scenes"
    - character_id: "turtle"
      reference_images: ["assets/characters/turtle.png"]
      physical_scale:
        body_length_cm: 180
        shell_length_cm: 125
        shoulder_height_cm: 95
      relative_scale_rules:
        - "turtle remains rideable for hero"

scenes:
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_2"
      character_ids: ["hero", "turtle"]
      object_ids: []
      prompt: "story"
      output: "assets/scenes/scene10.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)

        hero = guides.character_bible[0]
        turtle = guides.character_bible[1]
        self.assertEqual(hero.physical_scale.height_cm, 178)
        self.assertEqual(hero.physical_scale.silhouette_notes, ["adult natural build"])
        self.assertEqual(hero.relative_scale_rules, ["hero keeps the same body scale across scenes"])
        self.assertEqual(turtle.physical_scale.body_length_cm, 180)
        self.assertEqual(turtle.physical_scale.shell_length_cm, 125)
        self.assertEqual(turtle.physical_scale.shoulder_height_cm, 95)
        self.assertEqual(scenes[0].image_character_ids, ["hero", "turtle"])

    def test_parse_manifest_supports_still_image_plan_mode_on_cuts(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p1"
          output: "assets/scenes/scene10_1.png"
      - cut_id: 2
        still_image_plan:
          mode: reuse_anchor
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p2"
          output: "assets/scenes/scene10_2.png"
```
"""
        yaml_text = mod.extract_yaml_block(md)
        _, scenes = mod.parse_manifest_yaml(yaml_text)

        self.assertEqual([s.still_image_plan_mode for s in scenes], ["generate_still", "reuse_anchor"])

    def test_parse_manifest_supports_dotted_ids_and_still_assets(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
scenes:
  - scene_id: 3.1
    cuts:
      - cut_id: 2.1
        still_assets:
          - asset_id: "temple_day"
            role: "primary"
            output: "assets/scenes/temple_day.png"
            image_generation:
              tool: "google_nanobanana_2"
              prompt: "temple"
              output: "assets/scenes/temple_day.png"
              references: []
              location_ids: ["sea_temple"]
              location_variant_ids: ["altar_day"]
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, scenes = mod.parse_manifest_yaml(yaml_text)

        self.assertEqual(len(scenes), 1)
        self.assertEqual(scenes[0].scene_id, "scene3.1_cut2.1")
        self.assertEqual(scenes[0].selector, "scene3.1_cut2.1")
        self.assertEqual(scenes[0].manifest_scene_id, "3.1")
        self.assertEqual(scenes[0].image_location_ids, ["sea_temple"])
        self.assertEqual(scenes[0].image_location_variant_ids, ["altar_day"])
        self.assertEqual(scenes[0].still_assets[0]["asset_id"], "temple_day")
        self.assertEqual(scenes[0].image_output, "assets/scenes/temple_day.png")

    def test_story_image_generation_defaults_to_generate_still_only(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        ref_scene = mod.SceneSpec(
            scene_id="0",
            manifest_scene_id="0",
            selector="scene0",
            kind="character_reference",
            reference_id="hero_ref",
            timestamp=None,
            duration_seconds=None,
            still_image_plan_mode=None,
            image_tool="google_nanobanana_2",
            image_prompt="ref",
            image_output="assets/characters/hero.png",
            image_references=[],
            image_character_ids=[],
            image_character_ids_present=False,
            image_character_variant_ids=[],
            image_character_variant_ids_present=False,
            image_object_ids=[],
            image_object_ids_present=False,
            image_object_variant_ids=[],
            image_object_variant_ids_present=False,
            image_location_ids=[],
            image_location_ids_present=False,
            image_location_variant_ids=[],
            image_location_variant_ids_present=False,
            image_aspect_ratio=None,
            image_size=None,
            video_tool=None,
            video_input_image=None,
            video_first_frame=None,
            video_last_frame=None,
            video_motion_prompt=None,
            video_output=None,
            narration_tool=None,
            narration_text=None,
            narration_tts_text=None,
            narration_output=None,
            narration_normalize_to_scene_duration=True,
            narration_silence_intentional=False,
            narration_silence_confirmed_by_human=False,
            narration_silence_kind=None,
            narration_silence_reason=None,
            still_assets=[],
        )
        generate_scene = mod.SceneSpec(
            **{
                **ref_scene.__dict__,
                "scene_id": "scene10_cut1",
                "manifest_scene_id": "10",
                "selector": "scene10_cut1",
                "kind": None,
                "image_output": "assets/scenes/scene10_1.png",
                "still_image_plan_mode": "generate_still",
            }
        )
        reuse_scene = mod.SceneSpec(
            **{
                **ref_scene.__dict__,
                "scene_id": "scene10_cut2",
                "manifest_scene_id": "10",
                "selector": "scene10_cut2",
                "kind": None,
                "image_output": "assets/scenes/scene10_2.png",
                "still_image_plan_mode": "reuse_anchor",
            }
        )
        bridge_scene = mod.SceneSpec(
            **{
                **ref_scene.__dict__,
                "scene_id": "scene10_cut3",
                "manifest_scene_id": "10",
                "selector": "scene10_cut3",
                "kind": None,
                "image_output": "assets/scenes/scene10_3.png",
                "still_image_plan_mode": "no_dedicated_still",
            }
        )

        allowed_modes = {"generate_still"}
        self.assertTrue(mod._should_generate_image_scene(ref_scene, allowed_story_modes=allowed_modes, base_dir=repo_root))
        self.assertTrue(mod._should_generate_image_scene(generate_scene, allowed_story_modes=allowed_modes, base_dir=repo_root))
        self.assertFalse(mod._should_generate_image_scene(reuse_scene, allowed_story_modes=allowed_modes, base_dir=repo_root))
        self.assertFalse(mod._should_generate_image_scene(bridge_scene, allowed_story_modes=allowed_modes, base_dir=repo_root))

        recreate_scene = mod.SceneSpec(
            **{
                **ref_scene.__dict__,
                "scene_id": "scene10_cut4",
                "manifest_scene_id": "10",
                "selector": "scene10_cut4",
                "kind": None,
                "image_output": "assets/scenes/scene10_4.png",
                "still_image_plan_mode": "reuse_anchor",
                "still_image_generation_status": "recreate",
            }
        )
        created_scene = mod.SceneSpec(
            **{
                **ref_scene.__dict__,
                "scene_id": "scene10_cut5",
                "manifest_scene_id": "10",
                "selector": "scene10_cut5",
                "kind": None,
                "image_output": "assets/scenes/scene10_5.png",
                "still_image_plan_mode": "generate_still",
                "still_image_generation_status": "created",
            }
        )
        self.assertTrue(mod._should_generate_image_scene(recreate_scene, allowed_story_modes=allowed_modes, base_dir=repo_root))
        self.assertFalse(mod._should_generate_image_scene(created_scene, allowed_story_modes=allowed_modes, base_dir=repo_root))


if __name__ == "__main__":
    unittest.main()
