import importlib.util
import sys
import unittest
from pathlib import Path


def _load_generate_assets_module(repo_root: Path):
    script = repo_root / "scripts" / "generate-assets-from-manifest.py"
    spec = importlib.util.spec_from_file_location("generate_assets_from_manifest_silent", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


class TestSilentNarration(unittest.TestCase):
    def test_validate_scene_narration_allows_silent_tool_with_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
scenes:
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_2"
      character_ids: []
      object_ids: []
      prompt: "scene"
      output: "assets/scenes/scene10.png"
      references: []
    video_generation:
      tool: "kling_3_0"
      duration_seconds: 4
      output: "assets/scenes/scene10.mp4"
    audio:
      narration:
        tool: "silent"
        text: ""
        tts_text: ""
        silence_contract:
          intentional: true
          kind: "visual_value_hold"
          confirmed_by_human: true
          reason: "映像で見せる価値が大きい追加カット"
        output: "assets/audio/scene10.mp3"
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, _, scenes = mod.parse_manifest_yaml_full(yaml_text)

        mod.validate_scene_narration(scenes=scenes, require=True, scene_filter=None)

    def test_validate_scene_narration_rejects_silent_tool_without_contract(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_generate_assets_module(repo_root)

        md = """# Manifest

```yaml
scenes:
  - scene_id: 10
    image_generation:
      tool: "google_nanobanana_2"
      character_ids: []
      object_ids: []
      prompt: "scene"
      output: "assets/scenes/scene10.png"
      references: []
    video_generation:
      tool: "kling_3_0"
      duration_seconds: 4
      output: "assets/scenes/scene10.mp4"
    audio:
      narration:
        tool: "silent"
        text: ""
        output: "assets/audio/scene10.mp3"
```
"""

        yaml_text = mod.extract_yaml_block(md)
        _, _, scenes = mod.parse_manifest_yaml_full(yaml_text)

        with self.assertRaises(SystemExit) as ctx:
            mod.validate_scene_narration(scenes=scenes, require=True, scene_filter=None)
        self.assertIn("silence_contract.intentional=true", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
