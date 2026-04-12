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

    def test_removes_stateful_next_cut_language_from_request(self) -> None:
        prompt = """[連続性]
この cut 単体で、太郎が宴の最中に故郷を思い出しはじめたと分かるようにする。次の cut で太郎が帰りたいと言い出しても不自然にならない感情の橋渡しにする。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene08_cut01.png",
            references=["assets/characters/urashima.png"],
            topic="浦島太郎",
        )
        self.assertIn("この画像だけで、太郎が宴の最中に故郷を思い出しはじめたと分かるようにする。", rewritten)
        self.assertNotIn("次の cut", rewritten)
        self.assertNotIn("感情の橋渡し", rewritten)

    def test_drops_reference_section_when_references_are_empty(self) -> None:
        prompt = """[シーン]
海底神殿の奥に、まだ動いていない巨大な砂時計がある。

[参照画像の使い方]
参照画像は使わない。

[禁止]
文字なし。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene03_7_cut01.png",
            references=[],
            topic="浦島太郎",
        )
        self.assertNotIn("[参照画像の使い方]", rewritten)
        self.assertNotIn("参照画像は使わない。", rewritten)

    def test_relabels_reference_paths_in_prompt_body(self) -> None:
        prompt = """[参照画像の使い方]
`assets/characters/urashima.png` は顔立ちの基準として使う。`assets/characters/urashima_refstrip.png` は側面確認に使う。`assets/locations/banquet_hall_main.png` は空間構成の基準として使う。
"""
        rewritten = MODULE._rewrite_request_prompt_for_review(
            prompt=prompt,
            output="assets/scenes/scene07_cut01.png",
            references=[
                "assets/characters/urashima.png",
                "assets/characters/urashima_refstrip.png",
                "assets/locations/banquet_hall_main.png",
            ],
            topic="浦島太郎",
        )
        self.assertIn("人物参照画像1", rewritten)
        self.assertIn("人物参照画像2", rewritten)
        self.assertIn("場所参照画像1", rewritten)
        self.assertNotIn("assets/characters/urashima.png", rewritten)
        self.assertNotIn("assets/locations/banquet_hall_main.png", rewritten)

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
            self.assertTrue((tmp_path / "p000_index.md").exists())
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

    def test_resolve_image_reference_paths_uses_archived_self_reference_when_output_was_moved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archived_path = tmp_path / "assets" / "test" / "scene01_cut01__recreate_backup.png"
            archived_path.parent.mkdir(parents=True, exist_ok=True)
            archived_path.write_bytes(b"old-image")

            refs = MODULE._resolve_image_reference_paths(
                base_dir=tmp_path,
                reference_strings=["assets/scenes/scene01_cut01.png"],
                output_ref="assets/scenes/scene01_cut01.png",
                archived_self_reference_path=archived_path,
                test_image_dir="assets/test",
                dry_run=False,
                scene_selector="scene1_cut1",
            )

            self.assertEqual(refs, [archived_path])

    def test_resolve_image_reference_paths_finds_latest_backup_for_missing_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            archive_dir = tmp_path / "assets" / "test"
            archive_dir.mkdir(parents=True, exist_ok=True)
            older = archive_dir / "scene01_cut01__recreate_backup_20260412_100000.png"
            newer = archive_dir / "scene01_cut01__recreate_backup_20260412_110000.png"
            older.write_bytes(b"old")
            newer.write_bytes(b"new")

            refs = MODULE._resolve_image_reference_paths(
                base_dir=tmp_path,
                reference_strings=["assets/scenes/scene01_cut01.png"],
                output_ref="assets/scenes/scene01_cut01.png",
                archived_self_reference_path=None,
                test_image_dir="assets/test",
                dry_run=False,
                scene_selector="scene1_cut1",
            )

            self.assertEqual(refs, [newer])

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
            self.assertTrue((tmp_path / "p000_index.md").exists())
            self.assertIn("`人物参照画像1`: `assets/characters/urashima.png`", request_text)
            self.assertIn("`小道具参照画像1`: `assets/objects/tamatebako.png`", request_text)
            self.assertIn("`場所参照画像1`: `assets/locations/banquet_hall_main.png`", request_text)

    def test_materialized_requests_preserve_explicit_scene_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            (tmp_path / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
            (tmp_path / "assets" / "objects").mkdir(parents=True, exist_ok=True)
            for rel in [
                "assets/scenes/scene01_cut01.png",
                "assets/objects/tamatebako.png",
            ]:
                (tmp_path / rel).write_bytes(b"x")
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
assets:
  object_bible:
    - object_id: tamatebako
      reference_images: ["assets/objects/tamatebako.png"]
      fixed_prompts: ["box"]
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "google_nanobanana_2"
          object_ids: ["tamatebako"]
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "参照画像1の構図を維持し、玉手箱だけを直す。"
          output: "assets/scenes/scene01_cut01.png"
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
            self.assertIn("`参照画像1`: `assets/scenes/scene01_cut01.png`", request_text)
            self.assertIn("`小道具参照画像1`: `assets/objects/tamatebako.png`", request_text)

    def test_build_image_scene_dependencies_tracks_inter_scene_refs_only(self) -> None:
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
        image_generation:
          tool: "google_nanobanana_2"
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
      - cut_id: 2
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "google_nanobanana_2"
          references: ["assets/scenes/scene01_cut01.png"]
          prompt: "p2"
          output: "assets/scenes/scene01_cut02.png"
      - cut_id: 3
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "google_nanobanana_2"
          references: []
          prompt: "p3"
          output: "assets/scenes/scene01_cut03.png"
```
""",
                encoding="utf-8",
            )

            metadata, guides, scenes = MODULE.parse_manifest_yaml_full(MODULE.extract_yaml_block(manifest_path.read_text(encoding="utf-8")))
            deps = MODULE._build_image_scene_dependencies(scenes)

            self.assertEqual(deps["scene1_cut1"], set())
            self.assertEqual(deps["scene1_cut2"], {"scene1_cut1"})
            self.assertEqual(deps["scene1_cut3"], set())

    def test_materialized_requests_include_source_requests_for_image_and_video(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
human_change_requests:
  - request_id: "hr-001"
    status: verified
    raw_request: "scene1_cut1 の玉手箱を asset に合わせて直す。"
    resolution_notes: "箱の見た目を黒漆と金意匠に統一"
  - request_id: "hr-002"
    status: verified
    raw_request: "scene1_cut1 の人物を老いた浦島太郎に直す。"
    resolution_notes: ""
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        implementation_trace:
          source_request_ids: ["hr-001", "hr-002"]
          status: implemented
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
          applied_request_ids: ["hr-002", "hr-001"]
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene01_cut01.mp4"
          applied_request_ids: ["hr-001", "hr-002"]
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

            image_request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")

            self.assertIn("- source_requests:", image_request_text)
            self.assertIn("`hr-002`: scene1_cut1 の人物を老いた浦島太郎に直す。", image_request_text)
            self.assertIn(
                "`hr-001`: scene1_cut1 の玉手箱を asset に合わせて直す。 (resolution_notes: 箱の見た目を黒漆と金意匠に統一)",
                image_request_text,
            )
            self.assertLess(image_request_text.index("`hr-002`"), image_request_text.index("`hr-001`"))

            self.assertIn("- source_requests:", video_request_text)
            self.assertIn("`hr-001`: scene1_cut1 の玉手箱を asset に合わせて直す。", video_request_text)
            self.assertIn("`hr-002`: scene1_cut1 の人物を老いた浦島太郎に直す。", video_request_text)
            self.assertLess(video_request_text.index("`hr-001`"), video_request_text.index("`hr-002`"))

    def test_materialized_requests_omit_source_requests_without_applied_request_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
human_change_requests:
  - request_id: "hr-001"
    status: verified
    raw_request: "scene1_cut1 を直す。"
    resolution_notes: ""
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "p1"
          output: "assets/scenes/scene01_cut01.png"
        video_generation:
          tool: "kling_3_0_omni"
          motion_prompt: "m1"
          output: "assets/videos/scene01_cut01.mp4"
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

            image_request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
            video_request_text = (tmp_path / "video_generation_requests.md").read_text(encoding="utf-8")

            self.assertNotIn("- source_requests:", image_request_text)
            self.assertNotIn("- source_requests:", video_request_text)

    def test_validate_human_change_requests_rejects_unknown_applied_request_ids(self) -> None:
        manifest = {
            "human_change_requests": [
                {
                    "request_id": "hr-001",
                    "status": "verified",
                    "raw_request": "scene1_cut1 を直す。",
                }
            ],
            "scenes": [
                {
                    "scene_id": "1",
                    "cuts": [
                        {
                            "cut_id": "1",
                            "implementation_trace": {
                                "source_request_ids": ["hr-001"],
                                "status": "implemented",
                            },
                            "image_generation": {
                                "tool": "google_nanobanana_2",
                                "prompt": "p1",
                                "output": "assets/scenes/scene01_cut01.png",
                                "applied_request_ids": ["hr-999"],
                            },
                        }
                    ],
                }
            ],
        }

        with self.assertRaises(SystemExit) as ctx:
            MODULE.validate_human_change_requests(manifest=manifest, scene_filter=None)

        self.assertIn("unknown human_change_request id(s) in image_generation", str(ctx.exception))

    def test_scene7_onward_request_prefers_script_visual_beat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            script_path = tmp_path / "script.md"
            manifest_path.write_text(
                """# Manifest

```yaml
video_metadata:
  topic: "浦島太郎"
scenes:
  - scene_id: 7
    cuts:
      - cut_id: 1
        still_image_plan:
          mode: generate_still
        image_generation:
          tool: "google_nanobanana_2"
          prompt: "既存の prompt"
          output: "assets/scenes/scene07_cut01.png"
```
""",
                encoding="utf-8",
            )
            script_path.write_text(
                """# Script

```yaml
scenes:
  - scene_id: 7
    cuts:
      - cut_id: 1
        visual_beat: "宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎。"
        human_review:
          approved_visual_beat: "竜宮城の宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎。"
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
            self.assertIn("[場面の核]", request_text)
            self.assertIn("竜宮城の宴会エリアで楽しむ他のキャラクターたちに囲まれる中、頭をかかえる浦島太郎。", request_text)
            self.assertIn("既存の prompt", request_text)

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
            self.assertTrue((tmp_path / "p000_index.md").exists())

            exclusion_text = (tmp_path / "generation_exclusion_report.md").read_text(encoding="utf-8")
            self.assertIn("scene6_cut1", exclusion_text)
            self.assertIn("story removal", exclusion_text)
            self.assertIn("assets/videos/scene06_cut01.mp4", exclusion_text)
            self.assertIn("assets/audio/scene06_cut01_narration.mp3", exclusion_text)


if __name__ == "__main__":
    unittest.main()
