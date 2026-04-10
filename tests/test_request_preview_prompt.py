from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate-assets-from-manifest.py"
SPEC = importlib.util.spec_from_file_location("generate_assets_from_manifest", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TestRequestPreviewPrompt(unittest.TestCase):
    def test_rewrites_stateful_character_asset_wording(self) -> None:
        prompt = """[登場人物]
浦島太郎の参照画像（以後のsceneで一貫性を保つため）。

[小道具 / 舞台装置]
参照画像のため背景小道具は置かない。

[連続性]
後続sceneでも顔立ち、髪型、衣装の形、体格比率を変えないための基準画像にする。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/characters/urashima.png",
            references=[],
            topic="浦島太郎",
        )
        self.assertIn("物語「浦島太郎」に出てくる浦島太郎のキャラクター基準画像。", rewritten)
        self.assertIn("基準画像のため背景小道具は置かない。", rewritten)
        self.assertIn("顔立ち、髪型、衣装の形、体格比率を読み取れる基準画像にする。", rewritten)
        self.assertNotIn("後続scene", rewritten)
        self.assertNotIn("以後のscene", rewritten)
        self.assertNotIn("この cut", rewritten)

    def test_rewrites_reference_usage_for_cut_requests(self) -> None:
        prompt = """[登場人物]
参照画像と完全一致（顔、髪型、衣装、甲羅パターン）。

[小道具 / 舞台装置]
連続性アンカー: 海亀の甲羅の模様、朝の光の方向、波の質感。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene01_cut01.png",
            references=["assets/characters/urashima.png", "assets/characters/turtle.png"],
            topic="浦島太郎",
        )
        self.assertIn("この画像は物語「浦島太郎」の一場面を視覚化する。", rewritten)
        self.assertIn("参照画像に写っている顔、髪型、衣装、甲羅パターンをこの場面でも維持する。", rewritten)
        self.assertIn("参照画像に写っている海亀の甲羅の模様、朝の光の方向、波の質感を、この場面の画面内でも維持する。", rewritten)
        self.assertNotIn("連続性アンカー", rewritten)
        self.assertNotIn("この cut", rewritten)

    def test_materialized_requests_include_reuse_and_bridge_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
          generation_status: created
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p1"
          output: "assets/scenes/scene01_1.png"
      - cut_id: 2
        still_image_plan:
          mode: reuse_anchor
          generation_status: recreate
          source: "scene01_cut01"
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p2"
          output: "assets/scenes/scene01_2.png"
      - cut_id: 3
        still_image_plan:
          mode: no_dedicated_still
          source: "motion chain: scene01_cut01 -> scene02_cut01"
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p3"
          output: "assets/scenes/scene01_3.png"
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("## scene1_cut2", request_text)
            self.assertIn("- still_mode: `reuse_anchor`", request_text)
            self.assertIn("- generation_status: `recreate`", request_text)
            self.assertIn("- plan_source: `scene01_cut01`", request_text)
            self.assertIn("## scene1_cut3", request_text)
            self.assertIn("- still_mode: `no_dedicated_still`", request_text)
            self.assertIn("motion chain: scene01_cut01 -> scene02_cut01", request_text)

    def test_recreate_archives_existing_image_to_test_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            image_path = tmp_path / "assets" / "scenes" / "scene01_1.png"
            image_path.parent.mkdir(parents=True, exist_ok=True)
            image_path.write_bytes(b"old-image")

            MODULE._archive_existing_image_for_recreate(
                out_path=image_path,
                base_dir=tmp_path,
                test_image_dir="assets/test",
            )

            self.assertFalse(image_path.exists())
            archived = list((tmp_path / "assets" / "test").glob("scene01_1__recreate_backup_*.png"))
            self.assertEqual(len(archived), 1)
            self.assertEqual(archived[0].read_bytes(), b"old-image")

    def test_materialized_requests_include_resolved_asset_references(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            (tmp_path / "assets" / "characters").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "objects").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "locations").mkdir(parents=True, exist_ok=True)
            for rel in [
                "assets/characters/urashima.png",
                "assets/objects/tamatebako.png",
                "assets/locations/banquet_hall_main.png",
            ]:
                (tmp_path / rel).write_bytes(b"x")
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
assets:
  character_bible:
    - character_id: urashima
      reference_images: ["assets/characters/urashima.png"]
  object_bible:
    - object_id: tamatebako
      reference_images: ["assets/objects/tamatebako.png"]
      fixed_prompts: ["box"]
  location_bible:
    - location_id: banquet_hall_main
      reference_images: ["assets/locations/banquet_hall_main.png"]
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "google_nanobanana_2"
          character_ids: ["urashima"]
          object_ids: ["tamatebako"]
          location_ids: ["banquet_hall_main"]
          prompt: "p1"
          output: "assets/scenes/scene01_1.png"
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertIn("assets/characters/urashima.png", request_text)
            self.assertIn("assets/objects/tamatebako.png", request_text)
            self.assertIn("assets/locations/banquet_hall_main.png", request_text)

    def test_deleted_cuts_are_excluded_from_requests_and_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 6
    cuts:
      - cut_id: 1
        cut_status: deleted
        deletion_reason: "story removal"
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p1"
          output: "assets/scenes/scene06_cut01.png"
        audio:
          narration:
            tool: "silent"
            text: ""
            output: "assets/audio/scene06_cut01_narration.mp3"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene06_cut01.mp4"
      - cut_id: 2
        still_image_plan:
          mode: generate_still
          generation_status: created
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p2"
          output: "assets/scenes/scene06_cut02.png"
```
""",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--materialize-request-files-only",
                    "--skip-audio",
                    "--skip-image-prompt-review",
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            self.assertNotIn("scene6_cut1", request_text)
            self.assertIn("scene6_cut2", request_text)

            exclusion_text = (tmp_path / "generation_exclusion_report.md").read_text(encoding="utf-8")
            self.assertIn("scene6_cut1", exclusion_text)
            self.assertIn("story removal", exclusion_text)
            self.assertIn("assets/videos/scene06_cut01.mp4", exclusion_text)
            self.assertIn("assets/audio/scene06_cut01_narration.mp3", exclusion_text)


if __name__ == "__main__":
    unittest.main()
