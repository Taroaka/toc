from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "scripts" / "render-video.sh"
BUILD_CLIP_LISTS_PATH = REPO_ROOT / "scripts" / "build-clip-lists.py"


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe required")
class TestRenderVideo(unittest.TestCase):
    def _ffprobe_duration(self, path: Path) -> float:
        return float(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ],
                text=True,
            ).strip()
        )

    def _make_video(self, path: Path, duration: int, color: str) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"color=c={color}:s=320x180:d={duration}:r=24",
                "-vf",
                "format=yuv420p",
                "-an",
                str(path),
            ],
            check=True,
            cwd=REPO_ROOT,
        )

    def _make_mp3(self, path: Path, duration: int, frequency: int) -> None:
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"sine=frequency={frequency}:duration={duration}",
                "-c:a",
                "libmp3lame",
                "-q:a",
                "2",
                str(path),
            ],
            check=True,
            cwd=REPO_ROOT,
        )

    def test_render_video_supports_two_video_clips_and_three_narration_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            video1 = tmp_path / "scene03_cut01.mp4"
            video2 = tmp_path / "scene03_cut02.mp4"
            audio1 = tmp_path / "scene03_cut01_narration.mp3"
            audio2 = tmp_path / "scene03_cut02_narration.mp3"
            audio3 = tmp_path / "scene03_cut03_narration.mp3"
            clips = tmp_path / "video_clips.txt"
            narrations = tmp_path / "video_narration_list.txt"
            out = tmp_path / "scene03_compiled.mp4"

            self._make_video(video1, duration=2, color="red")
            self._make_video(video2, duration=3, color="blue")
            self._make_mp3(audio1, duration=1, frequency=440)
            self._make_mp3(audio2, duration=2, frequency=550)
            self._make_mp3(audio3, duration=2, frequency=660)

            clips.write_text(
                "\n".join(
                    [
                        f"file '{video1}'",
                        f"file '{video2}'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            narrations.write_text(
                "\n".join(
                    [
                        f"file '{audio1}'",
                        f"file '{audio2}'",
                        f"file '{audio3}'",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "bash",
                    str(SCRIPT_PATH),
                    "--clip-list",
                    str(clips),
                    "--narration-list",
                    str(narrations),
                    "--out",
                    str(out),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            self.assertTrue(out.exists())
            duration = self._ffprobe_duration(out)
            self.assertGreater(duration, 4.8)
            self.assertLess(duration, 5.3)

    def test_scene3_render_unit_lists_compile_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            assets_dir = tmp_path / "assets"
            videos_dir = assets_dir / "videos"
            audio_dir = assets_dir / "audio"
            videos_dir.mkdir(parents=True, exist_ok=True)
            audio_dir.mkdir(parents=True, exist_ok=True)

            manifest_path = tmp_path / "video_manifest.md"
            out = tmp_path / "scene03_compiled.mp4"

            self._make_video(videos_dir / "scene03_cut01.mp4", duration=2, color="red")
            self._make_video(videos_dir / "scene03_cut02.mp4", duration=3, color="blue")
            self._make_mp3(audio_dir / "scene03_cut01_narration.mp3", duration=1, frequency=440)
            self._make_mp3(audio_dir / "scene03_cut02_narration.mp3", duration=2, frequency=550)
            self._make_mp3(audio_dir / "scene03_cut03_narration.mp3", duration=2, frequency=660)

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
                    str(BUILD_CLIP_LISTS_PATH),
                    "--manifest",
                    str(manifest_path),
                    "--out-dir",
                    str(tmp_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            subprocess.run(
                [
                    "bash",
                    str(SCRIPT_PATH),
                    "--clip-list",
                    str(tmp_path / "video_clips.txt"),
                    "--narration-list",
                    str(tmp_path / "video_narration_list.txt"),
                    "--out",
                    str(out),
                ],
                check=True,
                cwd=REPO_ROOT,
            )

            self.assertTrue(out.exists())
            clips_text = (tmp_path / "video_clips.txt").read_text(encoding="utf-8")
            narrations_text = (tmp_path / "video_narration_list.txt").read_text(encoding="utf-8")
            self.assertEqual(clips_text.count("file '"), 2)
            self.assertEqual(narrations_text.count("file '"), 3)
            self.assertNotIn("scene03_cut03.mp4", clips_text)
            self.assertIn("scene03_cut03_narration.mp3", narrations_text)

            duration = self._ffprobe_duration(out)
            self.assertGreater(duration, 4.8)
            self.assertLess(duration, 5.3)


if __name__ == "__main__":
    unittest.main()
