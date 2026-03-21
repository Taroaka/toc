#!/usr/bin/env python3
"""
End-to-end runner for the immersive (cinematic) workflow.

This script:
1) Reads an existing script.md (scene descriptions, narration, prompts)
2) Builds an immersive-ride oriented video_manifest.md in a new run dir
3) Calls paid APIs (Gemini Image/Veo + ElevenLabs) via existing helpers
4) Renders the final video.mp4

Important:
- This WILL call paid APIs unless you stop earlier.
- It performs basic preflight checks to avoid obvious costly mistakes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.env import load_env_files  # noqa: E402
from toc.immersive_manifest import DEFAULT_IMMERSIVE_STORY_SCENE_STEP  # noqa: E402
from toc.providers.elevenlabs import DEFAULT_ELEVENLABS_VOICE_ID  # noqa: E402


def sanitize_topic(topic: str) -> str:
    topic = topic.strip().replace(" ", "_")
    topic = re.sub(r"[\\/]+", "_", topic)
    topic = re.sub(r"[^0-9A-Za-z_一-龠ぁ-んァ-ンー]+", "_", topic)
    topic = re.sub(r"_+", "_", topic).strip("_")
    return topic or "topic"


def default_timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M")


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ...``` block found in script.md")
    return m.group(1)


def must_env(name: str) -> str:
    v = os.environ.get(name) or ""
    if not v.strip():
        raise SystemExit(f"Missing env var: {name}")
    return v


def must_kling_credentials() -> None:
    has_gateway_key = bool((os.environ.get("KLING_API_KEY") or "").strip())
    has_official_keys = bool((os.environ.get("KLING_ACCESS_KEY") or "").strip()) and bool((os.environ.get("KLING_SECRET_KEY") or "").strip())
    if not (has_gateway_key or has_official_keys):
        raise SystemExit("Missing Kling credentials (set KLING_API_KEY or KLING_ACCESS_KEY+KLING_SECRET_KEY).")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def build_manifest_from_script(
    *,
    topic: str,
    created_at: str,
    scenes: list[dict],
    max_scenes: int | None,
    video_tool: str,
    out_path: Path,
) -> None:
    selected = scenes[: max_scenes or len(scenes)]
    if len(selected) < 2:
        raise SystemExit("Need at least 2 scenes to generate transitions (scene1->scene2).")

    narration_lines: list[str] = []
    for s in selected:
        t = (((s.get("audio") or {}).get("narration") or {}).get("text") or "").strip()
        if t:
            narration_lines.append(t)
    narration_text = "\n".join(narration_lines).strip() or "TBD"

    manifest: dict = {
        "video_metadata": {
            "topic": topic,
            "source_story": "",
            "created_at": created_at,
            "duration_seconds": 0,
            "aspect_ratio": "16:9",
            "resolution": "1280x720",
            "frame_rate": 24,
        },
        "assets": {
            "character_bible": [
                {
                    "character_id": "protagonist",
                    "reference_images": ["assets/characters/protagonist_front.png"],
                    "fixed_prompts": [
                        "photorealistic, cinematic, practical effects, 8K quality, ultra detailed textures",
                        "Character must match reference exactly (same face, hair, outfit).",
                        "Viewpoint is scene-dependent (POV or third-person), but must not drift within a single cut.",
                    ],
                    "notes": "Generate character turnaround references first and reuse as reference in scenes where this character appears.",
                }
            ],
            "style_guide": {
                "visual_style": "photorealistic, cinematic, practical effects",
                "forbidden": ["animated", "animation", "cartoon", "anime", "illustrated", "drawing", "watermark", "text"],
                "reference_images": [],
            },
        },
        "scenes": [],
    }

    # scene 0: protagonist character reference (turnaround; guide is narration-only)
    manifest["scenes"].append(
        {
            "scene_id": 0,
            "reference_id": "protagonist_front_ref",
            "timestamp": "00:00-00:08",
            "kind": "character_reference",
            "image_generation": {
                "tool": "google_nanobanana_pro",
                "prompt": (
                    "Photorealistic cinematic full-body character reference for the story protagonist.\n"
                    "Head-to-toe, feet visible, neutral background, neutral pose. No text in image."
                ),
                "output": "assets/characters/protagonist_front.png",
                "aspect_ratio": "16:9",
                "image_size": "2K",
                "references": [],
                "iterations": 4,
                "selected": None,
            },
        }
    )

    # scene images + transitions
    for idx, s in enumerate(selected, start=1):
        scene_id = idx * DEFAULT_IMMERSIVE_STORY_SCENE_STEP
        visual = s.get("visual") or {}
        loc = (visual.get("location") or {}) if isinstance(visual, dict) else {}

        scene_name = (s.get("scene_name") or s.get("sceneName") or f"Scene {idx}").strip()
        setting = (loc.get("setting") or "").strip()
        time_of_day = (loc.get("time_of_day") or loc.get("timeOfDay") or "").strip()
        weather = (loc.get("weather") or "").strip()
        props = loc.get("props") or []
        if not isinstance(props, list):
            props = []

        # IMPORTANT: Avoid child depiction. We intentionally do NOT reuse the original script's generation_prompt
        # because Momotaro scenes often include a "young boy" and Veo can RAI-filter photorealistic children.
        gen_prompt = "\n".join(
            [
                f"Practical theme park set representing the world of {topic}.",
                f"Scene: {scene_name}.",
                f"Setting: {setting or 'TBD'}.",
                f"Time: {time_of_day or 'TBD'}. Weather: {weather or 'TBD'}.",
                ("Props: " + ", ".join(str(p) for p in props[:12])) if props else "Props: TBD.",
                "Do not depict children. Use adult protagonist only (no visual guide character).",
            ]
        ).strip()

        motion_prompt = (((visual.get("motion_prompt")) or "").strip() if isinstance(visual, dict) else "")
        if not motion_prompt:
            motion_prompt = "カメラが滑らかに前進し、連続性を維持する（フェード/カットなし）。"
        else:
            motion_prompt = "カメラが滑らかに前進し、連続性を維持する（フェード/カットなし）。" + motion_prompt

        item: dict = {
            "scene_id": scene_id,
            "timestamp": f"00:{(idx-1)*8:02d}-00:{idx*8:02d}",
            "image_generation": {
                "tool": "google_nanobanana_pro",
                "prompt": gen_prompt,
                "output": f"assets/scenes/scene{scene_id}.png",
                "aspect_ratio": "16:9",
                "image_size": "2K",
                "references": [
                    "assets/characters/protagonist_front.png",
                    "assets/characters/protagonist_side.png",
                    "assets/characters/protagonist_back.png",
                ],
                "iterations": 4,
                "selected": None,
            },
        }

        # transitions (idx -> idx+1)
        if idx < len(selected):
            next_scene_id = (idx + 1) * DEFAULT_IMMERSIVE_STORY_SCENE_STEP
            item["video_generation"] = {
                "tool": video_tool,
                "duration_seconds": 8,
                "first_frame": f"assets/scenes/scene{scene_id}.png",
                "last_frame": f"assets/scenes/scene{next_scene_id}.png",
                "motion_prompt": motion_prompt,
                "output": f"assets/scenes/scene{scene_id}_to_{next_scene_id}.mp4",
            }

        # single narration track (attach to first generated scene)
        if idx == 1:
            item["audio"] = {
                "narration": {
                    "text": narration_text,
                    "tool": "elevenlabs",
                    "output": "assets/audio/narration.mp3",
                    "normalize_to_scene_duration": False,
                }
            }

        manifest["scenes"].append(item)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    md = "# Video Manifest Output (Immersive)\n\n```yaml\n"
    md += yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True).rstrip()
    md += "\n```\n"
    out_path.write_text(md, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="E2E run: script.md -> immersive manifest -> assets -> final video.")
    parser.add_argument("--topic", default="桃太郎")
    parser.add_argument(
        "--source-script",
        default="output/momotaro_20260110_1700/script.md",
        help="Existing script.md to read scenes/narration from.",
    )
    parser.add_argument("--timestamp", default=None)
    parser.add_argument("--run-dir", default=None, help="Override output run dir.")
    parser.add_argument("--base", default="output")
    parser.add_argument("--max-scenes", type=int, default=3, help="Limit scenes for cost control (default: 3).")
    parser.add_argument("--max-api-failures", type=int, default=3, help="Stop after N paid API failures (default: 3).")
    parser.add_argument("--elevenlabs-voice-id", default=None, help="Override ELEVENLABS_VOICE_ID for this run.")
    parser.add_argument(
        "--tts-ja",
        action="store_true",
        help="Force Japanese TTS instruction prefix/suffix (recommended for Japanese voice_id).",
    )
    parser.add_argument(
        "--skip-audio",
        action="store_true",
        help="Skip TTS and render a silent final video (recommended while iterating on visuals).",
    )
    parser.add_argument(
        "--videos-only",
        action="store_true",
        help="Reuse existing images and generate videos only (implies --skip-audio).",
    )
    parser.add_argument(
        "--chain-seconds-from-end",
        type=float,
        default=0.042,
        help="When chaining videos, extract the next first-frame from this many seconds before the previous video's end.",
    )
    parser.add_argument(
        "--video-tool",
        choices=["kling", "kling-omni", "seedance", "veo"],
        default="kling-omni",
        help='Video generation tool in manifest ("kling"=kling_3_0, "kling-omni"=kling_3_0_omni, "seedance"=seedance). "veo" is mapped to Kling for safety.',
    )

    # Prompt overrides applied at API-call time (not baked into manifest).
    parser.add_argument(
        "--image-prompt-prefix",
        default=(
            "Photorealistic, cinematic, practical effects. 8K quality, ultra detailed textures.\n"
            "No on-screen text. No watermark.\n"
            "Viewpoint is scene-dependent (POV or third-person), but must not drift within a single cut."
        ),
        help="Prepended to every image prompt.",
    )
    parser.add_argument(
        "--image-prompt-suffix",
        default=(
            "Avoid: animated, animation, cartoon, anime, illustrated, drawing, watermark, logos.\n"
            "Maintain consistent characters and continuity."
        ),
        help="Appended to every image prompt.",
    )
    parser.add_argument(
        "--video-prompt-prefix",
        default=(
            "Photorealistic cinematic footage.\n"
            "Single continuous take. No cuts, no fade out, no crossfades, no dissolves.\n"
            "Do not switch scenes halfway. No shot change; continuity must be maintained throughout the entire clip.\n"
            "The environment should evolve continuously as the camera moves forward (no jump transitions).\n"
            "Seamless continuity between first and last frame; natural lighting transition."
        ),
        help="Prepended to every video prompt.",
    )
    parser.add_argument(
        "--video-prompt-suffix",
        default="Avoid: animated, cartoon, anime, illustrated, watermark. Keep motion smooth and readable.",
        help="Appended to every video prompt.",
    )
    parser.add_argument(
        "--video-negative-prompt",
        default=(
            "fade out, fade to black, crossfade, dissolve, cut, hard cut, montage, timelapse, jump cut, "
            "scene cut, shot change, camera cut, transition, "
            "title card, subtitle text, on-screen text, watermark"
        ),
        help="Negative prompt to reduce unwanted transitions inside a clip.",
    )

    args = parser.parse_args()

    load_env_files(repo_root=REPO_ROOT)

    if args.videos_only:
        args.skip_audio = True

    if args.video_tool == "veo":
        print("[warn] --video-tool veo is disabled for safety; using kling-omni instead.")
        args.video_tool = "kling-omni"

    # Preflight (avoid paid mistakes)
    if not args.videos_only:
        must_env("GEMINI_API_KEY")
    if args.video_tool in {"kling", "kling-omni"}:
        must_kling_credentials()
    if args.video_tool == "seedance":
        must_env("ARK_API_KEY")
    voice_id = ""
    if not args.skip_audio:
        must_env("ELEVENLABS_API_KEY")
        voice_id = (args.elevenlabs_voice_id or os.environ.get("ELEVENLABS_VOICE_ID") or "").strip()
        if not voice_id:
            voice_id = DEFAULT_ELEVENLABS_VOICE_ID
        if voice_id.lower() in {"your_voice_id", "voice_id_tbd", "tbd"}:
            print(
                "[warn] ELEVENLABS_VOICE_ID is a placeholder; falling back to default voice_id "
                f"({DEFAULT_ELEVENLABS_VOICE_ID})."
            )
            voice_id = DEFAULT_ELEVENLABS_VOICE_ID

    source_script = Path(args.source_script)
    if not source_script.exists():
        raise SystemExit(f"source script not found: {source_script}")

    topic_raw = args.topic
    ts = args.timestamp or default_timestamp()
    topic_slug = sanitize_topic(topic_raw)

    run_dir = Path(args.run_dir) if args.run_dir else (Path(args.base) / f"{topic_slug}_{ts}_immersive")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)

    # Build manifest from existing script
    script_md = source_script.read_text(encoding="utf-8")
    script_yaml = extract_yaml_block(script_md)
    data = yaml.safe_load(script_yaml) or {}
    scenes = data.get("scenes") or []
    if not isinstance(scenes, list):
        raise SystemExit("Invalid script.yaml: scenes is not a list")

    manifest_path = run_dir / "video_manifest.md"
    build_manifest_from_script(
        topic=topic_raw,
        created_at=dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        scenes=scenes,
        max_scenes=int(args.max_scenes) if args.max_scenes else None,
        video_tool=(
            "kling_3_0"
            if args.video_tool == "kling"
            else ("seedance" if args.video_tool == "seedance" else "kling_3_0_omni")
        ),
        out_path=manifest_path,
    )

    failures = 0
    try:
        tts_prefix = ""
        tts_suffix = ""
        if args.tts_ja:
            # Try to keep instructions from being spoken (best-effort). Some TTS models ignore bracketed directives.
            tts_prefix = "【指示（読み上げない）】日本語で出力。以下の本文のみを自然な日本語で読み上げてください。"
            tts_suffix = "【指示（読み上げない）】日本語で出力。"

        cmd = [
            sys.executable,
            "scripts/generate-assets-from-manifest.py",
            "--manifest",
            str(manifest_path),
            "--force",
            "--skip-images" if args.videos_only else "",
            "--image-aspect-ratio",
            "16:9",
            "--video-aspect-ratio",
            "16:9",
            "--video-resolution",
            "720p",
            "--character-reference-views",
            "front,side,back",
            "--character-reference-strip",
            "--image-prompt-prefix",
            args.image_prompt_prefix,
            "--image-prompt-suffix",
            args.image_prompt_suffix,
            "--video-prompt-prefix",
            args.video_prompt_prefix,
            "--video-prompt-suffix",
            args.video_prompt_suffix,
            "--video-negative-prompt",
            args.video_negative_prompt,
            "--tts-prompt-prefix",
            tts_prefix,
            "--tts-prompt-suffix",
            tts_suffix,
            "--enable-last-frame",
            "--chain-first-frame-from-prev-video",
            "--chain-first-frame-seconds-from-end",
            str(args.chain_seconds_from_end),
        ]
        cmd = [x for x in cmd if x]
        if args.skip_audio:
            cmd.append("--skip-audio")
        else:
            cmd += ["--elevenlabs-voice-id", voice_id]
        run(cmd)
    except subprocess.CalledProcessError:
        failures += 1
        if failures >= int(args.max_api_failures):
            raise SystemExit(f"Stopping: reached max paid API failures ({args.max_api_failures}).")
        raise

    run(
        [
            sys.executable,
            "scripts/build-clip-lists.py",
            "--manifest",
            str(manifest_path),
            "--out-dir",
            str(run_dir),
        ]
    )

    render_cmd = [
        "scripts/render-video.sh",
        "--clip-list",
        str(run_dir / "video_clips.txt"),
        "--fps",
        "24",
        "--size",
        "1280x720",
        "--out",
        str(run_dir / "video.mp4"),
    ]
    if not args.skip_audio:
        audio_path = run_dir / "assets" / "audio" / "narration.mp3"
        if not audio_path.exists():
            raise SystemExit(f"Expected narration audio not found: {audio_path}")
        render_cmd += ["--audio", str(audio_path)]

    run(render_cmd)

    print(f"Run dir: {run_dir.resolve()}")
    print(f"Wrote: {run_dir.resolve() / 'video.mp4'}")


if __name__ == "__main__":
    main()
