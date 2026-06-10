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

    def test_video_motion_collects_v3_cut_contract_motion_boundary(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_v3_") as td:
            run_dir = Path(td)
            manifest = {
                "scenes": [
                    {
                        "scene_id": 10,
                        "cuts": [
                            {
                                "cut_id": 1,
                                "cut_contract": {
                                    "source_event_contract": {
                                        "primary_event_beat_id": "scene10_event_pressure",
                                        "source_event_beat_ids": ["scene10_event_pressure"],
                                    },
                                    "motion_contract": {
                                        "source_event_beat_id": "scene10_event_pressure",
                                        "starts_from_first_frame": True,
                                        "must_not_advance_to_event_beat_ids": ["scene10_event_turn"],
                                        "motion_brief": "圧力の姿勢だけが小さく動く",
                                        "start_from_visible_state": "first_frame_contract.visible_start_state",
                                        "end_state": "turnの直前で止まる",
                                        "must_not_add": ["解決"],
                                    },
                                    "event_context_for_cut": {
                                        "derived_from": ["scene_event.event_sequence[]", "cut_contract.source_event_contract"],
                                        "editable": False,
                                        "primary_event_beat": {"beat_id": "scene10_event_pressure"},
                                    },
                                },
                                "video_generation": {
                                    "tool": "kling_3_0",
                                    "motion_prompt": "圧力の姿勢だけが小さく動く",
                                    "first_frame": "assets/scenes/scene10_cut01.png",
                                    "duration_seconds": 8,
                                    "output": "assets/videos/scene10_cut01.mp4",
                                },
                            }
                        ],
                    }
                ]
            }

            entries = collect_entries("video_motion", run_dir, manifest)

            self.assertEqual(len(entries), 1)
            entry = entries[0]
            self.assertFalse(entry["motion_contract_missing"])
            self.assertEqual(entry["motion_contract_required_fields_missing"], [])
            self.assertEqual(entry["motion_contract"]["source_event_beat_id"], "scene10_event_pressure")
            self.assertEqual(entry["source_event_contract"]["primary_event_beat_id"], "scene10_event_pressure")
            self.assertEqual(entry["event_context_for_cut"]["primary_event_beat"]["beat_id"], "scene10_event_pressure")

    def test_video_clip_semantic_stage_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported video semantic pack stage"):
                collect_entries("video_clip", run_dir)

    def test_video_clip_sample_frame_semantic_stage_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported video semantic pack stage"):
                collect_entries("video_clip", run_dir)

    def test_render_semantic_stage_is_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(MANIFEST, encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "unsupported video semantic pack stage"):
                collect_entries("render", run_dir)

    def test_rejects_unknown_stage(self) -> None:
        with tempfile.TemporaryDirectory(prefix="semantic_pack_video_") as td:
            with self.assertRaises(ValueError):
                collect_entries("asset_plan", Path(td), manifest={})


if __name__ == "__main__":
    unittest.main()
