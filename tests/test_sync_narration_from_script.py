from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from toc.harness import load_structured_document


REPO_ROOT = Path(__file__).resolve().parents[1]


class TestSyncNarrationFromScript(unittest.TestCase):
    def test_sync_prefers_human_review_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_narration_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"

            script_path.write_text(
                """# Script

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        narration: "漢字の台本です。"
        tts_text: "かんじの だいほんです。"
        human_review:
          status: "approved"
          notes: ""
          approved_narration: "承認した台本です。"
          approved_tts_text: "しょうにんした だいほんです。"
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        audio:
          narration:
            tool: "elevenlabs"
            text: "old"
            tts_text: "old"
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python",
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            _, manifest = load_structured_document(manifest_path)
            narration = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]
            self.assertEqual(narration["text"], "しょうにんした だいほんです。")
            self.assertEqual(narration["tts_text"], "しょうにんした だいほんです。")

    def test_sync_falls_back_to_cut_tts_text(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_narration_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"

            script_path.write_text(
                """# Script

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 2
        narration: "村へ帰ります。"
        tts_text: "むらへ かえります。"
        human_review:
          status: "pending"
          notes: ""
          approved_narration: ""
          approved_tts_text: ""
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 2
        audio:
          narration:
            tool: "elevenlabs"
            text: ""
            tts_text: ""
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python",
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            _, manifest = load_structured_document(manifest_path)
            narration = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]
            self.assertEqual(narration["text"], "むらへ かえります。")
            self.assertEqual(narration["tts_text"], "むらへ かえります。")

    def test_sync_materializes_tts_text_from_elevenlabs_prompt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_narration_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"

            script_path.write_text(
                """# Script

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 3
        narration: "彼女は駆けだします。"
        tts_text: ""
        elevenlabs_prompt:
          spoken_context: "かのじょは こえを ふるわせながら いいました。"
          voice_tags: ["excited", "laughs harder"]
          spoken_body: "やっと ここまで これました！"
          stability_profile: "creative"
        human_review:
          status: "pending"
          notes: ""
          approved_narration: ""
          approved_tts_text: ""
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 3
        audio:
          narration:
            tool: "elevenlabs"
            text: ""
            tts_text: ""
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python",
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            _, manifest = load_structured_document(manifest_path)
            narration = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]
            expected = "かのじょは こえを ふるわせながら いいました。 [excited][laughs harder] やっと ここまで これました！"
            self.assertEqual(narration["text"], expected)
            self.assertEqual(narration["tts_text"], expected)

    def test_sync_materializes_human_change_requests_and_still_assets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_human_changes_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"

            script_path.write_text(
                """# Script

```yaml
human_change_requests:
  - request_id: "req-1"
    source: "human_script_review"
    created_at: "2026-04-04T12:00:00+09:00"
    raw_request: "追加 still と参照を作る"
    original_selectors: ["scene35_cut2"]
    current_selectors: ["scene3.1_cut2.1"]
    normalized_actions:
      - action: "add_location_asset"
        payload:
          location_id: "sea_temple"
          reference_images: ["assets/locations/sea_temple.png"]
          reference_variants: []
          fixed_prompts: ["sea temple stone walls"]
          review_aliases: ["海底神殿"]
          continuity_notes: ["same temple"]
          notes: "shared location"
      - action: "renumber_scene"
        target:
          scene_id: "35"
        payload:
          new_scene_id: "3.1"
      - action: "renumber_cut"
        target:
          scene_id: "3.1"
          cut_id: "2"
        payload:
          new_cut_id: "2.1"
      - action: "create_still_asset"
        target:
          scene_id: "3.1"
          cut_id: "2.1"
        payload:
          asset_id: "temple_day"
          role: "primary"
          output: "assets/scenes/temple_day.png"
          image_generation:
            tool: "google_nanobanana_2"
            prompt: "temple day"
            output: "assets/scenes/temple_day.png"
            references: []
            location_ids: ["sea_temple"]
          direction_notes: ["wide establishing"]
      - action: "set_video_direction"
        target:
          scene_id: "3.1"
          cut_id: "2.1"
        payload:
          notes: ["background glimpse only"]
scenes:
  - scene_id: 3.1
    human_review:
      status: "approved"
      notes: ""
      approved_scene_summary: "神殿へ向かう。"
      approved_story_visual: "海底神殿の導入"
      change_request_ids: ["req-1"]
    cuts:
      - cut_id: 2.1
        narration: "しんでんへ むかいます。"
        tts_text: "しんでんへ むかいます。"
        visual_beat: "神殿の入口"
        human_review:
          status: "approved"
          notes: ""
          approved_narration: "しんでんへ むかいます。"
          approved_tts_text: "しんでんへ むかいます。"
          approved_visual_beat: "神殿の入口"
          approved_image_notes: ["temple should stay in background"]
          approved_video_notes: ["slow dolly in"]
          change_request_ids: ["req-1"]
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 35
    cuts:
      - cut_id: 2
        output: "assets/scenes/scene35_cut02.png"
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "old"
          output: "assets/scenes/scene35_cut02.png"
          character_ids: []
          object_ids: []
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 5
          first_frame_image: "assets/scenes/scene35_cut02.png"
        audio:
          narration:
            tool: "elevenlabs"
            text: ""
            tts_text: ""
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python",
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            _, manifest = load_structured_document(manifest_path)
            self.assertEqual(manifest["human_change_requests"][0]["request_id"], "req-1")
            self.assertEqual(manifest["assets"]["location_bible"][0]["location_id"], "sea_temple")
            scene = manifest["scenes"][0]
            self.assertEqual(str(scene["scene_id"]), "3.1")
            self.assertEqual(scene["scene_summary"], "神殿へ向かう。")
            self.assertEqual(scene["implementation_trace"]["source_request_ids"], ["req-1"])
            cut = scene["cuts"][0]
            self.assertEqual(str(cut["cut_id"]), "2.1")
            self.assertEqual(cut["output"], "assets/scenes/scene3.1_cut02.png")
            self.assertEqual(cut["still_assets"][0]["asset_id"], "temple_day")
            self.assertEqual(cut["image_generation"]["location_ids"], ["sea_temple"])
            self.assertEqual(cut["image_generation"]["output"], "assets/scenes/temple_day.png")
            self.assertEqual(cut["video_generation"]["first_frame_image"], "assets/scenes/scene3.1_cut02.png")
            self.assertEqual(cut["video_generation"]["direction_notes"], ["slow dolly in"])
            self.assertEqual(cut["audio"]["narration"]["applied_request_ids"], ["req-1"])

    def test_sync_adds_default_video_generation_for_remaining_story_cuts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_default_video_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"

            script_path.write_text(
                """# Script

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 2
        narration: "帰り道を進みます。"
        tts_text: "かえりみちを すすみます。"
        visual_beat: "浜辺を静かに進む"
        human_review:
          status: "approved"
          notes: ""
          approved_narration: ""
          approved_tts_text: ""
          approved_visual_beat: "浜辺を静かに進む"
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 2
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "beach path"
          output: "assets/scenes/scene01_cut02.png"
          character_ids: []
          object_ids: []
        audio:
          narration:
            tool: "elevenlabs"
            text: ""
            tts_text: ""
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python",
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            _, manifest = load_structured_document(manifest_path)
            cut = manifest["scenes"][0]["cuts"][0]
            self.assertEqual(cut["still_image_plan"]["mode"], "generate_still")
            video = cut["video_generation"]
            self.assertEqual(video["tool"], "kling_3_0_omni")
            self.assertEqual(video["output"], "assets/videos/scene01_cut02.mp4")
            self.assertEqual(video["first_frame"], "assets/scenes/scene01_cut02.png")
            self.assertEqual(video["duration_seconds"], 4)
            self.assertIn("浜辺を静かに進む", video["motion_prompt"])

    def test_sync_does_not_restore_deleted_cuts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_deleted_cut_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"

            script_path.write_text(
                """# Script

```yaml
human_change_requests:
  - request_id: "req-delete"
    source: "human_script_review"
    created_at: "2026-04-19T00:00:00+09:00"
    raw_request: "scene1_cut2 を削除する"
    original_selectors: ["scene1_cut2"]
    current_selectors: []
    normalized_actions:
      - action: "delete_cut"
        target:
          scene_id: "1"
          cut_id: "2"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        narration: "残すカットです。"
        tts_text: "のこす かっとです。"
        visual_beat: "残る"
        human_review:
          status: "approved"
          notes: ""
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "keep"
          output: "assets/scenes/scene01_cut01.png"
          character_ids: []
          object_ids: []
      - cut_id: 2
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "delete"
          output: "assets/scenes/scene01_cut02.png"
          character_ids: []
          object_ids: []
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python",
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            _, manifest = load_structured_document(manifest_path)
            cuts = manifest["scenes"][0]["cuts"]
            self.assertEqual([str(c["cut_id"]) for c in cuts], ["1"])

    def test_sync_does_not_backfill_cut_video_generation_when_scene_uses_render_units(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_render_units_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"

            script_path.write_text(
                """# Script

```yaml
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        narration: "ひとつめ"
        tts_text: "ひとつめ"
        visual_beat: "cut1"
      - cut_id: 2
        narration: "ふたつめ"
        tts_text: "ふたつめ"
        visual_beat: "cut2"
      - cut_id: 3
        narration: "みっつめ"
        tts_text: "みっつめ"
        visual_beat: "cut3"
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        image_generation:
          output: "assets/scenes/scene03_cut01.png"
      - cut_id: 2
        image_generation:
          output: "assets/scenes/scene03_cut02.png"
      - cut_id: 3
        image_generation:
          output: "assets/scenes/scene03_cut03.png"
    render_units:
      - unit_id: 1
        source_cut_ids: [1]
        video_generation:
          output: "assets/videos/scene03_cut01.mp4"
      - unit_id: 2
        source_cut_ids: [2, 3]
        video_generation:
          output: "assets/videos/scene03_cut02.mp4"
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python",
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            _, manifest = load_structured_document(manifest_path)
            cuts = manifest["scenes"][0]["cuts"]
            self.assertNotIn("video_generation", cuts[0])
            self.assertNotIn("video_generation", cuts[1])
            self.assertNotIn("video_generation", cuts[2])
            self.assertIn("render_units", manifest["scenes"][0])

    def test_sync_does_not_recreate_cut_video_generation_from_change_requests_when_scene_uses_render_units(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_sync_render_units_request_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"

            script_path.write_text(
                """# Script

```yaml
human_change_requests:
  - request_id: hr-201
    normalized_actions:
      - action: set_video_direction
        target:
          scene_id: 3
          cut_id: 2
        payload:
          notes:
            - "前進速度を上げる"
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        narration: "ひとつめ"
        tts_text: "ひとつめ"
        visual_beat: "cut1"
      - cut_id: 2
        narration: "ふたつめ"
        tts_text: "ふたつめ"
        visual_beat: "cut2"
      - cut_id: 3
        narration: "みっつめ"
        tts_text: "みっつめ"
        visual_beat: "cut3"
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        image_generation:
          output: "assets/scenes/scene03_cut01.png"
      - cut_id: 2
        image_generation:
          output: "assets/scenes/scene03_cut02.png"
      - cut_id: 3
        image_generation:
          output: "assets/scenes/scene03_cut03.png"
    render_units:
      - unit_id: 1
        source_cut_ids: [1]
        video_generation:
          output: "assets/videos/scene03_cut01.mp4"
      - unit_id: 2
        source_cut_ids: [2, 3]
        video_generation:
          output: "assets/videos/scene03_cut02.mp4"
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python",
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            _, manifest = load_structured_document(manifest_path)
            cuts = manifest["scenes"][0]["cuts"]
            self.assertNotIn("video_generation", cuts[0])
            self.assertNotIn("video_generation", cuts[1])
            self.assertNotIn("video_generation", cuts[2])
            self.assertIn("render_units", manifest["scenes"][0])


if __name__ == "__main__":
    unittest.main()
