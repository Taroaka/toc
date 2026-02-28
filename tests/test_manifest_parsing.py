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


if __name__ == "__main__":
    unittest.main()
