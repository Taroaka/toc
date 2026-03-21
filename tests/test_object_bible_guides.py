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


class TestObjectBibleGuides(unittest.TestCase):
    def test_object_bible_merges_refs_and_injects_props_section(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  object_bible:
    - object_id: "ryugu_palace"
      kind: "setpiece"
      reference_images:
        - "assets/objects/ryugu_palace_exterior.png"
      fixed_prompts:
        - "Ryugu Palace exterior: living coral + mother-of-pearl inlays, wet sheen, realistic scale"
      cinematic:
        role: "Threshold + temptation"
        visual_takeaways:
          - "This place is alive"
        spectacle_details:
          - "Distant fish-school light show in the atrium"

scenes:
  - scene_id: 1
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: []
      object_ids: ["ryugu_palace"]
      prompt: |
        [GLOBAL / INVARIANTS]
        base global

        [PROPS / SETPIECES]

        [SCENE]
        ref scene
      output: "assets/objects/ryugu_palace_exterior.png"
      references: []
  - scene_id: 2
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: []
      object_ids: ["ryugu_palace"]
      prompt: |
        [GLOBAL / INVARIANTS]
        base global

        [PROPS / SETPIECES]
        base props

        [SCENE]
        story scene
      output: "assets/scenes/scene2.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)
        for scene in scenes:
            mod.apply_asset_guides_to_scene(scene=scene, guides=guides, character_refs_mode="scene")

        ref_scene = scenes[0]
        story_scene = scenes[1]

        # Reference scene should avoid self-reference.
        self.assertNotIn("assets/objects/ryugu_palace_exterior.png", ref_scene.image_references)

        # Story scene should include the object reference image.
        self.assertIn("assets/objects/ryugu_palace_exterior.png", story_scene.image_references)

        # Prompt should include object fixed prompt and cinematic lines under PROPS / SETPIECES.
        lines = story_scene.image_prompt.splitlines()
        idx_props = lines.index("[PROPS / SETPIECES]")
        self.assertIn("Ryugu Palace exterior: living coral + mother-of-pearl inlays, wet sheen, realistic scale", lines)
        self.assertIn("映画での役割: Threshold + temptation", lines)
        self.assertIn("映像から伝える情報: This place is alive", lines)
        self.assertIn("見せ場ディテール: Distant fish-school light show in the atrium", lines)
        self.assertEqual(lines[idx_props + 1], "Ryugu Palace exterior: living coral + mother-of-pearl inlays, wet sheen, realistic scale")

    def test_require_object_ids_fails_when_missing(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  object_bible:
    - object_id: "tamatebako"
      kind: "artifact"
      reference_images: ["assets/objects/tamatebako.png"]
      fixed_prompts: ["Tamatebako: ornate lacquer + gold inlay; no engraved text"]

scenes:
  - scene_id: 1
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: []
      # object_ids intentionally missing
      prompt: |
        [GLOBAL / INVARIANTS]
        base
      output: "assets/scenes/scene1.png"
      references: []
  - scene_id: 2
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: []
      object_ids: ["tamatebako"]
      prompt: "ref"
      output: "assets/objects/tamatebako.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)

        with self.assertRaises(SystemExit) as ctx:
            mod.validate_scene_object_ids(scenes=scenes, guides=guides, require=True, scene_filter=None)
        self.assertIn("missing image_generation.object_ids", str(ctx.exception))

    def test_require_object_reference_scenes_fails_when_missing_output(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  object_bible:
    - object_id: "ryugu_palace"
      kind: "setpiece"
      reference_images: ["assets/objects/ryugu_palace.png"]
      fixed_prompts: ["Ryugu Palace"]

scenes:
  - scene_id: 1
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: []
      object_ids: ["ryugu_palace"]
      prompt: "p"
      output: "assets/scenes/scene1.png"
      references: []
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, guides, scenes = mod.parse_manifest_yaml_full(yaml_text)

        with self.assertRaises(SystemExit) as ctx:
            mod.validate_object_reference_scenes(scenes=scenes, guides=guides, require=True)
        self.assertIn("Missing object reference scenes", str(ctx.exception))

    def test_object_variant_selectors_use_only_selected_variant_refs(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
assets:
  object_bible:
    - object_id: "amulet"
      reference_images: ["assets/objects/amulet_default.png"]
      fixed_prompts: ["amulet base"]
      reference_variants:
        - variant_id: "amulet_pristine"
          reference_images: ["assets/objects/amulet_pristine.png"]
          fixed_prompts: ["no cracks"]
        - variant_id: "amulet_corrupted"
          reference_images: ["assets/objects/amulet_corrupted.png"]
          fixed_prompts: ["hairline cracks and dark aura"]

scenes:
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: []
      object_ids: ["amulet"]
      object_variant_ids: ["amulet_corrupted"]
      prompt: |
        [PROPS / SETPIECES]
        base props

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

        self.assertEqual(scenes[0].image_references, ["assets/objects/amulet_corrupted.png"])
        self.assertIn("amulet base", scenes[0].image_prompt)
        self.assertIn("hairline cracks and dark aura", scenes[0].image_prompt)
        self.assertNotIn("no cracks", scenes[0].image_prompt)


if __name__ == "__main__":
    unittest.main()
