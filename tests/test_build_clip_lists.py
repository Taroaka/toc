from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "build-clip-lists.py"


class TestBuildClipLists(unittest.TestCase):
    def test_deleted_cuts_are_skipped_from_concat_lists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 6
    cuts:
      - cut_id: 1
        cut_status: deleted
        deletion_reason: "story removal"
        image_generation:
          output: "assets/scenes/scene06_cut01.png"
        audio:
          narration:
            output: "assets/audio/scene06_cut01_narration.mp3"
        video_generation:
          output: "assets/videos/scene06_cut01.mp4"
      - cut_id: 2
        audio:
          narration:
            output: "assets/audio/scene06_cut02_narration.mp3"
        video_generation:
          output: "assets/videos/scene06_cut02.mp4"
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
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            clips_text = (tmp_path / "video_clips.txt").read_text(encoding="utf-8")
            narration_text = (tmp_path / "video_narration_list.txt").read_text(encoding="utf-8")
            exclusions_text = (tmp_path / "video_generation_exclusions.md").read_text(encoding="utf-8")
            self.assertTrue((tmp_path / "p000_index.md").exists())

            self.assertIn("scene06_cut02.mp4", clips_text)
            self.assertNotIn("scene06_cut01.mp4", clips_text)
            self.assertIn("scene06_cut02_narration.mp3", narration_text)
            self.assertNotIn("scene06_cut01_narration.mp3", narration_text)
            self.assertIn("scene6_cut1", exclusions_text)
            self.assertIn("story removal", exclusions_text)

    def test_render_units_drive_video_lists_while_narration_keeps_cut_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        audio:
          narration:
            output: "assets/audio/scene03_cut01_narration.mp3"
        video_generation:
          output: "assets/videos/scene03_cut01.mp4"
      - cut_id: 2
        audio:
          narration:
            output: "assets/audio/scene03_cut02_narration.mp3"
        video_generation:
          output: "assets/videos/scene03_cut02.mp4"
      - cut_id: 3
        audio:
          narration:
            output: "assets/audio/scene03_cut03_narration.mp3"
        video_generation:
          output: "assets/videos/scene03_cut03.mp4"
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
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            clips_text = (tmp_path / "video_clips.txt").read_text(encoding="utf-8")
            narration_text = (tmp_path / "video_narration_list.txt").read_text(encoding="utf-8")

            self.assertEqual(clips_text.count("file '"), 2)
            self.assertIn("scene03_cut01.mp4", clips_text)
            self.assertIn("scene03_cut02.mp4", clips_text)
            self.assertNotIn("scene03_cut03.mp4", clips_text)

            self.assertEqual(narration_text.count("file '"), 3)
            self.assertLess(
                narration_text.index("scene03_cut01_narration.mp3"),
                narration_text.index("scene03_cut02_narration.mp3"),
            )
            self.assertLess(
                narration_text.index("scene03_cut02_narration.mp3"),
                narration_text.index("scene03_cut03_narration.mp3"),
            )

    def test_render_units_require_full_unique_cut_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        audio:
          narration:
            output: "assets/audio/scene03_cut01_narration.mp3"
      - cut_id: 2
        audio:
          narration:
            output: "assets/audio/scene03_cut02_narration.mp3"
      - cut_id: 3
        audio:
          narration:
            output: "assets/audio/scene03_cut03_narration.mp3"
    render_units:
      - unit_id: 1
        source_cut_ids: [1]
        video_generation:
          output: "assets/videos/scene03_cut01.mp4"
      - unit_id: 2
        source_cut_ids: [2]
        video_generation:
          output: "assets/videos/scene03_cut02.mp4"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("non-deleted cuts missing from render_units", result.stderr + result.stdout)

    def test_render_units_reject_duplicate_cut_assignment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            manifest_path = tmp_path / "video_manifest.md"
            manifest_path.write_text(
                """# Manifest

```yaml
scenes:
  - scene_id: 3
    cuts:
      - cut_id: 1
        audio:
          narration:
            output: "assets/audio/scene03_cut01_narration.mp3"
      - cut_id: 2
        audio:
          narration:
            output: "assets/audio/scene03_cut02_narration.mp3"
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        video_generation:
          output: "assets/videos/scene03_cut01.mp4"
      - unit_id: 2
        source_cut_ids: [2]
        video_generation:
          output: "assets/videos/scene03_cut02.mp4"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--manifest",
                    str(manifest_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cuts assigned to multiple render_units", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
