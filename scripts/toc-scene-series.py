#!/usr/bin/env python3
"""
Scaffold a "scene-series" run:

- Extract questions from `story.md` or `script.md`
- Create `series_plan.md`
- Create per-scene folders:
  output/<topic>_<timestamp>/scenes/sceneXX/{evidence.md,script.md,video_manifest.md,assets/**}

This is the implementation helper for the Claude Code slash command `/toc-scene-series`.

Note:
- Visual style (real vs abstract) is intentionally left as placeholder.
- By default this only scaffolds files. Use `--placeholder-e2e` to also render placeholder videos.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass
class SceneQuestion:
    scene_id: int
    main_text: str | None
    question: str | None


def sanitize_topic(topic: str) -> str:
    topic = topic.strip().replace(" ", "_")
    topic = re.sub(r"[\\/]+", "_", topic)
    topic = re.sub(r"[^0-9A-Za-z_一-龠ぁ-んァ-ンー]+", "_", topic)
    topic = re.sub(r"_+", "_", topic).strip("_")
    return topic or "topic"


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def default_timestamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M")


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def append_state_block(state_path: Path, kv: dict[str, str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in kv.items()]
    block = "\n".join(lines) + "\n---\n"
    with state_path.open("a", encoding="utf-8") as f:
        f.write(block)


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise ValueError("No ```yaml ...``` block found.")
    return m.group(1)


def parse_yaml_scalar(value: str) -> str | None:
    v = value.strip()
    if v == "" or v.lower() == "null":
        return None
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        return v[1:-1]
    return v


def iter_kv_lines(yaml_text: str) -> Iterable[tuple[int, list[str], str, str]]:
    """
    A minimal YAML-ish iterator:
    - Tracks key context by indentation
    - Yields (indent, context_keys, key, value)
    """
    stack: list[tuple[int, str]] = []

    def push(indent: int, key: str) -> None:
        nonlocal stack
        while stack and indent <= stack[-1][0]:
            stack.pop()
        stack.append((indent, key))

    for raw in yaml_text.splitlines():
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if stripped.startswith("- "):
            stripped = stripped[2:].strip()

        if ":" not in stripped:
            continue

        key, value = stripped.split(":", 1)
        key = key.strip()
        value = value.strip()

        push(indent, key)
        context_keys = [k for _, k in stack]
        yield indent, context_keys, key, value


def extract_questions_from_story(story_path: Path) -> list[SceneQuestion]:
    md = story_path.read_text(encoding="utf-8")
    yaml_text = extract_yaml_block(md)

    scenes: list[SceneQuestion] = []
    current: SceneQuestion | None = None

    for _, ctx, key, value in iter_kv_lines(yaml_text):
        if key == "scene_id" and "scenes" in ctx and "script" in ctx:
            if current:
                scenes.append(current)
            try:
                scene_id = int(parse_yaml_scalar(value) or "0")
            except ValueError:
                scene_id = len(scenes) + 1
            current = SceneQuestion(scene_id=scene_id, main_text=None, question=None)
            continue

        if not current:
            continue

        if "text_overlay" in ctx:
            if key == "main":
                current.main_text = parse_yaml_scalar(value)
            elif key == "sub":
                current.question = parse_yaml_scalar(value)

    if current:
        scenes.append(current)

    return scenes


def extract_questions_from_script(script_path: Path) -> list[SceneQuestion]:
    md = script_path.read_text(encoding="utf-8")
    yaml_text = extract_yaml_block(md)

    scenes: list[SceneQuestion] = []
    current: SceneQuestion | None = None

    for _, ctx, key, value in iter_kv_lines(yaml_text):
        if key == "scene_id" and "scenes" in ctx:
            if current:
                scenes.append(current)
            try:
                scene_id = int(parse_yaml_scalar(value) or "0")
            except ValueError:
                scene_id = len(scenes) + 1
            current = SceneQuestion(scene_id=scene_id, main_text=None, question=None)
            continue

        if not current:
            continue

        if key == "content" and "text_overlay" in ctx and "main_text" in ctx:
            current.main_text = parse_yaml_scalar(value)
        elif key == "content" and "text_overlay" in ctx and "sub_text" in ctx:
            current.question = parse_yaml_scalar(value)

    if current:
        scenes.append(current)

    return scenes


def ensure_question_mark(question: str) -> str:
    q = question.strip()
    if not q:
        return q
    if q.endswith("?") or q.endswith("？"):
        return q
    return q + "？"


def format_mmss(seconds: int) -> str:
    seconds = max(0, int(seconds))
    mm = seconds // 60
    ss = seconds % 60
    return f"{mm:02d}:{ss:02d}"


def render_series_plan_md(
    *,
    topic: str,
    timestamp: str,
    created_at: str,
    min_seconds: int,
    max_seconds: int,
    source_story: Path | None,
    source_script: Path | None,
    scenes: list[SceneQuestion],
    default_target_seconds: int,
) -> str:
    story_ref = str(source_story) if source_story else f"output/{topic}_{timestamp}/story.md"
    script_ref = str(source_script) if source_script else f"output/{topic}_{timestamp}/script.md"

    lines = [
        "# Series Plan (DRAFT)",
        "",
        "```yaml",
        "series_plan_metadata:",
        f'  topic: "{topic}"',
        f'  source_story: "{story_ref}"',
        f'  source_script: "{script_ref}"',
        f'  created_at: "{created_at}"',
        f"  min_seconds: {min_seconds}",
        f"  max_seconds: {max_seconds}",
        "",
        "scenes:",
    ]

    if not scenes:
        lines += [
            "  - scene_id: 1",
            '    main_text: "TBD"',
            '    question: "TBD?"',
            f"    target_seconds: {default_target_seconds}",
            '    notes: "No scenes found in story/script yet."',
        ]
    else:
        for s in scenes:
            q = ensure_question_mark(s.question or "TBD")
            main = s.main_text or "TBD"
            lines += [
                f"  - scene_id: {s.scene_id}",
                f'    main_text: "{main}"',
                f'    question: "{q}"',
                f"    target_seconds: {default_target_seconds}",
                '    notes: ""',
            ]

    lines += ["```", ""]
    return "\n".join(lines)


def render_evidence_md(scene_id: int, question: str) -> str:
    return "\n".join(
        [
            f"# Evidence (Scene {scene_id:02d})",
            "",
            "## Question",
            "",
            question,
            "",
            "## Answer (short)",
            "",
            "TBD",
            "",
            "## Evidence bullets",
            "",
            "- TBD",
            "- TBD",
            "- TBD",
            "",
            "## Sources",
            "",
            "- TBD",
            "",
            "## Gaps / Notes",
            "",
            "- TBD",
            "",
        ]
    )


def render_scene_script_md(topic: str, scene_id: int, target_seconds: int, main_text: str, question: str) -> str:
    return "\n".join(
        [
            "# Scene Script (Q&A) (DRAFT)",
            "",
            "```yaml",
            "scene_script_metadata:",
            f'  topic: "{topic}"',
            f"  scene_id: {scene_id}",
            f"  target_seconds: {target_seconds}",
            f'  question: "{question}"',
            "",
            "narration:",
            f'  hook: "{question}"',
            '  answer: "TBD"',
            "  evidence:",
            '    - "TBD"',
            '    - "TBD"',
            '    - "TBD"',
            '  close: "TBD"',
            "",
            "text_overlay:",
            f'  main_text: "{main_text}"',
            f'  sub_text: "{question}"',
            "",
            "notes:",
            '  - "Visual style (real/abstract) is deferred; keep prompts flexible."',
            "```",
            "",
        ]
    )


def render_scene_manifest_md(
    *,
    topic: str,
    run_dir: Path,
    scene_id: int,
    target_seconds: int,
    main_text: str,
    question: str,
) -> str:
    created_at = now_iso()
    ts_end = format_mmss(target_seconds)
    timestamp_range = f"00:00-{ts_end}"

    scene_dir = run_dir / "scenes" / f"scene{scene_id:02d}"
    source_scene_script = scene_dir / "script.md"

    # Keep prompts as placeholders (real/abstract decision deferred).
    image_prompt = (
        "TODO: Visual for answering the question.\n"
        "- Prefer explainable visuals (diagram/abstract) unless a realistic reenactment is explicitly desired.\n"
        "- No text in the image; overlays handled separately.\n"
    )

    motion_prompt = "TODO: minimal camera movement; keep it readable for overlays."
    narration_text = f"TODO: Answer '{question}' with evidence (30–60s)."

    lines = [
        "# Scene Video Manifest Output (DRAFT)",
        "",
        "```yaml",
        "video_metadata:",
        f'  topic: "{topic}"',
        f'  source_run: "{run_dir.as_posix()}/"',
        f'  source_scene_script: "{source_scene_script.as_posix()}"',
        f'  created_at: "{created_at}"',
        f"  duration_seconds: {target_seconds}",
        '  aspect_ratio: "9:16"',
        '  resolution: "1080x1920"',
        "",
        "assets:",
        "  style_guide:",
        '    visual_style: "tbd"',
        "    reference_images: []",
        "",
        "scenes:",
        f"  - scene_id: {scene_id}",
        f'    timestamp: "{timestamp_range}"',
        "    image_generation:",
        '      tool: "google_nanobanana_pro"',
        "      prompt: |",
    ]
    lines += ["        " + ln for ln in image_prompt.rstrip().splitlines()]
    lines += [
        f'      output: "assets/scenes/scene{scene_id}_base.png"',
        "      iterations: 4",
        "      selected: null",
        "    video_generation:",
        f'      tool: "{video_tool}"',
        f'      input_image: "assets/scenes/scene{scene_id}_base.png"',
        f'      motion_prompt: "{motion_prompt}"',
        f'      output: "assets/scenes/scene{scene_id}_video.mp4"',
        "    audio:",
        "      narration:",
        f'        text: "{narration_text}"',
        '        tool: "elevenlabs"',
        f'        output: "assets/audio/scene{scene_id}_narration.mp3"',
        "      bgm:",
        "        source: null",
        "        volume: 0.0",
        "      sfx: []",
        "    text_overlay:",
        f'      main_text: "{main_text}"',
        f'      sub_text: "{question}"',
        "",
        "final_output:",
        '  video_file: "video.mp4"',
        '  thumbnail: "thumb.png"',
        "",
        "quality_check:",
        "  visual_consistency: false",
        "  audio_sync: false",
        "  subtitle_readable: false",
        "  aspect_ratio_correct: true",
        "```",
        "",
    ]
    return "\n".join(lines)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold a scene-series run (Q&A per scene).")
    parser.add_argument("topic", help="Video topic.")
    parser.add_argument("--run-dir", default=None, help="Use an existing run dir instead of creating a new one.")
    parser.add_argument("--timestamp", default=None, help="Timestamp (YYYYMMDD_HHMM) used when creating run dir.")
    parser.add_argument("--base", default="output", help="Base output directory when creating run dir.")
    parser.add_argument("--min-seconds", type=int, default=30)
    parser.add_argument("--max-seconds", type=int, default=60)
    parser.add_argument("--default-seconds", type=int, default=None, help="Default per-scene seconds (default: min-seconds).")
    parser.add_argument("--scene-ids", default=None, help='Comma-separated list like "1,3,5" (default: all).')
    parser.add_argument("--force", action="store_true", help="Overwrite existing generated files.")
    parser.add_argument("--dry-run", action="store_true", help="Create folders/files only; do not render videos.")
    parser.add_argument(
        "--placeholder-e2e",
        action="store_true",
        help="Also generate placeholder assets and render per-scene videos (no external API).",
    )
    parser.add_argument(
        "--video-tool",
        choices=["kling", "kling-omni", "veo"],
        default="kling-omni",
        help='Video generation tool in manifests ("kling" uses kling_3_0, "kling-omni" uses kling_3_0_omni). "veo" is mapped to Kling for safety.',
    )

    args = parser.parse_args()

    topic_raw = args.topic
    topic_slug = sanitize_topic(topic_raw)
    ts = args.timestamp or default_timestamp()

    run_dir = Path(args.run_dir) if args.run_dir else (Path(args.base) / f"{topic_slug}_{ts}")
    ensure_dir(run_dir)
    if args.video_tool == "kling":
        video_tool = "kling_3_0"
    elif args.video_tool == "kling-omni":
        video_tool = "kling_3_0_omni"
    else:
        print('[warn] --video-tool veo is disabled for safety; using kling_3_0_omni instead.')
        video_tool = "kling_3_0_omni"

    # run-root defaults
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "job_id": f"JOB_{dt.datetime.now().strftime('%Y-%m-%d')}_{dt.datetime.now().strftime('%H%M%S')}",
                "topic": topic_raw,
                "status": "INIT",
                "runtime.stage": "scene_series",
            },
        )

    write_text(run_dir / "research.md", "# Research Output\n\nTBD\n", force=False)
    write_text(run_dir / "story.md", "# Story Script Output\n\nTBD\n", force=False)

    source_script = run_dir / "script.md"
    source_story = run_dir / "story.md"

    scenes: list[SceneQuestion] = []
    if source_script.exists():
        try:
            scenes = extract_questions_from_script(source_script)
        except ValueError:
            scenes = []
    if not scenes and source_story.exists():
        try:
            scenes = extract_questions_from_story(source_story)
        except ValueError:
            scenes = []

    scene_filter: set[int] | None = None
    if args.scene_ids:
        scene_filter = {int(x.strip()) for x in args.scene_ids.split(",") if x.strip()}
        scenes = [s for s in scenes if s.scene_id in scene_filter]

    default_target_seconds = args.default_seconds or args.min_seconds
    created_at = now_iso()

    series_plan_path = run_dir / "series_plan.md"
    series_plan_md = render_series_plan_md(
        topic=topic_raw,
        timestamp=ts,
        created_at=created_at,
        min_seconds=args.min_seconds,
        max_seconds=args.max_seconds,
        source_story=source_story if source_story.exists() else None,
        source_script=source_script if source_script.exists() else None,
        scenes=scenes,
        default_target_seconds=default_target_seconds,
    )
    write_text(series_plan_path, series_plan_md, force=args.force)

    scenes_root = run_dir / "scenes"
    ensure_dir(scenes_root)

    targets = scenes or [SceneQuestion(scene_id=1, main_text="TBD", question="TBD?")]

    for s in targets:
        scene_id = s.scene_id
        main_text = s.main_text or "TBD"
        question = ensure_question_mark(s.question or "TBD")
        scene_dir = scenes_root / f"scene{scene_id:02d}"

        # per-scene structure
        ensure_dir(scene_dir / "assets" / "characters")
        ensure_dir(scene_dir / "assets" / "styles")
        ensure_dir(scene_dir / "assets" / "scenes")
        ensure_dir(scene_dir / "assets" / "audio")
        ensure_dir(scene_dir / "logs")

        write_text(scene_dir / "evidence.md", render_evidence_md(scene_id, question), force=args.force)
        write_text(
            scene_dir / "script.md",
            render_scene_script_md(topic_raw, scene_id, default_target_seconds, main_text, question),
            force=args.force,
        )
        write_text(
            scene_dir / "video_manifest.md",
            render_scene_manifest_md(
                topic=topic_raw,
                run_dir=run_dir,
                scene_id=scene_id,
                target_seconds=default_target_seconds,
                main_text=main_text,
                question=question,
            ),
            force=args.force,
        )

        if args.placeholder_e2e and not args.dry_run:
            manifest_path = scene_dir / "video_manifest.md"
            run(["python", "scripts/generate-placeholder-assets.py", "--manifest", str(manifest_path), "--force"])
            run(
                [
                    "python",
                    "scripts/build-clip-lists.py",
                    "--manifest",
                    str(manifest_path),
                    "--out-dir",
                    str(scene_dir),
                ]
            )
            run(
                [
                    "scripts/render-video.sh",
                    "--clip-list",
                    str(scene_dir / "video_clips.txt"),
                    "--narration-list",
                    str(scene_dir / "video_narration_list.txt"),
                    "--out",
                    str(scene_dir / "video.mp4"),
                ]
            )

    append_state_block(
        state_path,
        {
            "timestamp": now_iso(),
            "topic": topic_raw,
            "status": "DONE",
            "runtime.stage": "scene_series_scaffolded",
            "artifact.series_plan": str(series_plan_path),
        },
    )

    print(f"Run dir: {run_dir}")
    print(f"Wrote: {series_plan_path}")
    print(f"Scenes: {len(targets)}")


if __name__ == "__main__":
    main()
