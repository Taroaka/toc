from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from toc.semantic_pack_video import collect_entries


MANIFEST = """# Manifest

```yaml
quality_check:
  review_contract:
    render_meaning: "final video preserves the approved story order"
render:
  output: "dist/final_story.mp4"
  sampled_frames:
    - "logs/review/semantic/render_frame001.jpg"
    - "logs/review/semantic/render_frame002.jpg"
  contact_sheet: "logs/review/semantic/render_contact_sheet.jpg"
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        cut_contract:
          target_beat: "Cinderella sees the invitation"
          must_show: ["Cinderella", "invitation"]
        video_generation:
          tool: "kling_3_0"
          motion_prompt: "Cinderella slowly lifts the invitation toward the window light."
          motion_contract:
            motion_intent: "Cinderella notices the invitation with restrained hope."
            must_preserve: ["Cinderella", "invitation", "window light"]
            must_not_add: ["palace arrival"]
            handoff_state: "The invitation is visible in her hand."
          first_frame: "assets/scenes/scene03_cut01.png"
          last_frame: "assets/scenes/scene03_cut01_end.png"
          duration_seconds: 6
          output: "assets/videos/scene03_cut01.mp4"
          contact_sheet: "logs/review/semantic/scene3_cut1_contact_sheet.jpg"
          retry_history:
            - status: "failed"
              reason: "provider timeout"
          retry_count: 1
      - cut_id: 2
        cut_status: deleted
        video_generation:
          motion_prompt: "deleted"
          output: "assets/videos/deleted.mp4"
  - scene_id: 4
    cuts:
      - cut_id: 1
        audio:
          narration:
            output: "assets/audio/scene04_cut01.mp3"
      - cut_id: 2
        audio:
          narration:
            output: "assets/audio/scene04_cut02.mp3"
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        semantic_contract:
          target_beat: "The coach leaves for the palace"
        video_generation:
          prompt: "The coach rolls away under lantern light."
          first_frame_image: "assets/scenes/scene04_cut01.png"
          sampled_frames:
            - "logs/review/semantic/scene4_unit1_frame001.jpg"
            - "logs/review/semantic/scene4_unit1_frame002.jpg"
          failures:
            - "first attempt drifted from coach"
          output: "assets/videos/scene04_unit01.mp4"
```
"""


class TestSemanticPackVideo(unittest.TestCase):
    def test_video_motion_collects_cut_and_render_unit_prompts(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")

            entries = collect_entries("video_motion", run_dir)

            selectors = [entry["selector"] for entry in entries]
            self.assertEqual(selectors, ["scene3_cut1", "scene4_unit1"])
            self.assertEqual(entries[0]["motion_prompt"], "Cinderella slowly lifts the invitation toward the window light.")
            self.assertEqual(entries[0]["semantic_contract"]["target_beat"], "Cinderella sees the invitation")
            self.assertFalse(entries[0]["motion_contract_missing"])
            self.assertEqual(entries[0]["motion_contract_required_fields_missing"], [])
            self.assertEqual(entries[0]["provider_history"][0]["status"], "failed")
            self.assertEqual(entries[0]["provider_history"][1]["provider_summary"]["retry_count"], 1)
            self.assertEqual(entries[1]["source_cut_ids"], [1, 2])
            self.assertEqual(entries[1]["motion_prompt"], "The coach rolls away under lantern light.")
            self.assertEqual(entries[1]["semantic_contract"]["target_beat"], "The coach leaves for the palace")
            self.assertTrue(entries[1]["motion_contract_missing"])
            self.assertEqual(
                entries[1]["motion_contract_required_fields_missing"],
                ["motion_intent", "must_preserve", "must_not_add", "handoff_state"],
            )

    def test_video_clip_collects_outputs_contact_sheet_and_sampled_frames(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")
            (run_dir / "assets" / "videos").mkdir(parents=True)
            (run_dir / "assets" / "videos" / "scene03_cut01.mp4").write_bytes(b"video")

            entries = collect_entries("video_clip", run_dir)

            first = entries[0]
            second = entries[1]
            self.assertEqual(first["selector"], "scene3_cut1")
            self.assertEqual(first["output"], "assets/videos/scene03_cut01.mp4")
            self.assertTrue(first["output_exists"])
            self.assertEqual(first["contact_sheet"], "logs/review/semantic/scene3_cut1_contact_sheet.jpg")
            self.assertTrue(first["contact_sheet_required"])
            self.assertFalse(first["contact_sheet_missing"])
            self.assertTrue(first["sampled_frames_missing"])
            self.assertEqual(first["provider_history"][0]["status"], "failed")
            self.assertEqual(second["selector"], "scene4_unit1")
            self.assertFalse(second["output_exists"])
            self.assertTrue(second["contact_sheet_missing"])
            self.assertFalse(second["sampled_frames_missing"])
            self.assertEqual(second["provider_history"][0]["failures"], ["first attempt drifted from coach"])
            self.assertEqual(
                second["sampled_frames"],
                [
                    "logs/review/semantic/scene4_unit1_frame001.jpg",
                    "logs/review/semantic/scene4_unit1_frame002.jpg",
                ],
            )

    def test_video_clip_discovers_sample_frame_directory_and_contact_sheet_files(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")
            frame_dir = run_dir / "assets" / "videos" / "scene03_cut01_frames"
            frame_dir.mkdir(parents=True)
            (frame_dir / "0001.jpg").write_bytes(b"jpg")
            (frame_dir / "0002.png").write_bytes(b"png")
            (run_dir / "assets" / "videos" / "scene03_cut01_contact_sheet.png").write_bytes(b"png")

            entries = collect_entries("video_clip", run_dir)

            self.assertEqual(entries[0]["sampled_frames"], ["assets/videos/scene03_cut01_frames/0001.jpg", "assets/videos/scene03_cut01_frames/0002.png"])
            self.assertEqual(entries[0]["contact_sheet"], "logs/review/semantic/scene3_cut1_contact_sheet.jpg")

    def test_render_collects_final_artifacts_and_concat_lists(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")
            (run_dir / "dist").mkdir()
            (run_dir / "dist" / "final_story.mp4").write_bytes(b"video")
            (run_dir / "video_clips.txt").write_text("file 'assets/videos/scene03_cut01.mp4'\n", encoding="utf-8")
            (run_dir / "video_narration_list.txt").write_text("file 'assets/audio/scene04_cut01.mp3'\n", encoding="utf-8")

            entries = collect_entries("render", run_dir)

            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertEqual(entry["selector"], "render")
            self.assertEqual(entry["semantic_contract"]["render_meaning"], "final video preserves the approved story order")
            self.assertIn({"path": "dist/final_story.mp4", "exists": True}, entry["final_outputs"])
            self.assertEqual(entry["clip_list"]["entry_count"], 1)
            self.assertEqual(entry["narration_list"]["entry_count"], 1)
            self.assertEqual(
                entry["render_order_materials"]["manifest_clip_order"],
                [
                    {"selector": "scene3_cut1", "output": "assets/videos/scene03_cut01.mp4"},
                    {"selector": "scene4_unit1", "source_cut_ids": [1, 2], "output": "assets/videos/scene04_unit01.mp4"},
                ],
            )
            self.assertEqual(entry["render_order_materials"]["concat_clip_order"], ["assets/videos/scene03_cut01.mp4"])
            self.assertEqual(
                entry["render_order_materials"]["manifest_narration_order"],
                [
                    {"selector": "scene4_cut1", "output": "assets/audio/scene04_cut01.mp3"},
                    {"selector": "scene4_cut2", "output": "assets/audio/scene04_cut02.mp3"},
                ],
            )
            self.assertEqual(entry["render_order_materials"]["concat_narration_order"], ["assets/audio/scene04_cut01.mp3"])
            self.assertEqual(
                entry["render_sample_refs"],
                [
                    {
                        "output": "dist/final_story.mp4",
                        "sampled_frames": ["logs/review/semantic/render_frame001.jpg", "logs/review/semantic/render_frame002.jpg"],
                        "sampled_frames_missing": False,
                        "contact_sheet": "logs/review/semantic/render_contact_sheet.jpg",
                        "contact_sheet_missing": False,
                    },
                    {
                        "output": "video.mp4",
                        "sampled_frames": ["logs/review/semantic/render_frame001.jpg", "logs/review/semantic/render_frame002.jpg"],
                        "sampled_frames_missing": False,
                        "contact_sheet": "logs/review/semantic/render_contact_sheet.jpg",
                        "contact_sheet_missing": False,
                    },
                    {
                        "output": "final.mp4",
                        "sampled_frames": ["logs/review/semantic/render_frame001.jpg", "logs/review/semantic/render_frame002.jpg"],
                        "sampled_frames_missing": False,
                        "contact_sheet": "logs/review/semantic/render_contact_sheet.jpg",
                        "contact_sheet_missing": False,
                    },
                    {
                        "output": "render.mp4",
                        "sampled_frames": ["logs/review/semantic/render_frame001.jpg", "logs/review/semantic/render_frame002.jpg"],
                        "sampled_frames_missing": False,
                        "contact_sheet": "logs/review/semantic/render_contact_sheet.jpg",
                        "contact_sheet_missing": False,
                    },
                    {
                        "output": "output.mp4",
                        "sampled_frames": ["logs/review/semantic/render_frame001.jpg", "logs/review/semantic/render_frame002.jpg"],
                        "sampled_frames_missing": False,
                        "contact_sheet": "logs/review/semantic/render_contact_sheet.jpg",
                        "contact_sheet_missing": False,
                    },
                ],
            )
            self.assertEqual(len(entry["clip_entries"]), 2)

    def test_rejects_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            with self.assertRaises(ValueError):
                collect_entries("asset_plan", Path(td), manifest={})


if __name__ == "__main__":
    unittest.main()
