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
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot


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
    append_state_snapshot(state_path, kv)


def parse_state_file(state_path: Path) -> dict[str, str]:
    if not state_path.exists():
        return {}
    merged: dict[str, str] = {}
    for raw in state_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().replace("\n", " ")
        if k:
            merged[k] = v
    return merged


def detect_hybridization_pending(md_text: str) -> bool:
    """
    Conservative detector for "hybridization requires human approval".

    We treat it as pending when:
    - YAML contains hybridization.approval_status: pending
    - OR any selection candidate requires_hybridization_approval: true

    If no YAML block exists, we fall back to a substring check.
    """
    try:
        yaml_text = extract_yaml_block(md_text)
    except Exception:
        t = md_text.lower()
        return ("approval_status: pending" in t) or ("requires_hybridization_approval: true" in t)

    pending = False
    for _, ctx, key, value in iter_kv_lines(yaml_text):
        if key == "approval_status" and "hybridization" in ctx:
            v = (parse_yaml_scalar(value) or "").strip().lower()
            if v == "pending":
                pending = True
        if key == "requires_hybridization_approval" and "candidates" in ctx and "selection" in ctx:
            v = (parse_yaml_scalar(value) or "").strip().lower()
            if v in {"true", "yes", "1"}:
                pending = True
    return pending


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
        "# シリーズプラン（DRAFT）",
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
            '    notes: "story/script から scene が見つからないため暫定。"',
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
            f"# 根拠（Scene {scene_id:02d}）",
            "",
            "## 質問",
            "",
            question,
            "",
            "## 結論（短く）",
            "",
            "TODO",
            "",
            "## 根拠（箇条書き）",
            "",
            "- TODO",
            "- TODO",
            "- TODO",
            "",
            "## ソース",
            "",
            "- TODO",
            "",
            "## 不確実点 / メモ",
            "",
            "- TODO",
            "",
        ]
    )


def render_scene_script_md(topic: str, scene_id: int, target_seconds: int, main_text: str, question: str) -> str:
    return "\n".join(
        [
            "# シーン台本（Q&A）（DRAFT）",
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
            '  answer: "TODO"',
            "  evidence:",
            '    - "TODO"',
            '    - "TODO"',
            '    - "TODO"',
            '  close: "TODO"',
            "",
            "text_overlay:",
            f'  main_text: "{main_text}"',
            f'  sub_text: "{question}"',
            "",
            "notes:",
            '  - "映像方針（現実寄り/抽象寄り）は後で確定する。プロンプトは柔軟に保つ。"',
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
    video_tool: str,
) -> str:
    created_at = now_iso()
    ts_end = format_mmss(target_seconds)
    timestamp_range = f"00:00-{ts_end}"

    scene_dir = run_dir / "scenes" / f"scene{scene_id:02d}"
    source_scene_script = scene_dir / "script.md"

    # Keep prompts as placeholders (real/abstract decision deferred).
    image_prompt = (
        "TODO: 質問に答えるための映像。\n"
        "- 実写再現が明確に望まれていない限り、説明可能なビジュアル（図解/抽象）を優先。\n"
        "- 画像内に文字を入れない（テロップは別で扱う）。\n"
    )

    motion_prompt = "TODO: 最小限のカメラ動き。テロップが読める可読性を優先。"

    # Cut planning (DRAFT):
    # - 1 cut = 1 narration
    # - main cut (at least 1): 5–15 seconds (based on actual narration audio duration)
    # - sub cuts (optional): 3–15 seconds (short 3–4s cuts are sub-only; not for single-cut narration)
    # - If narration would exceed 15s, split into multiple cuts
    # - Even if <= 15s, decide whether to split after both scene + narration are drafted

    def plan_cut_durations(total_seconds: int) -> list[tuple[str, int]]:
        max_seconds = 15
        min_main = 5
        min_sub = 3

        total = max(0, int(total_seconds))
        if total <= 0:
            return [("main", max_seconds)]

        if total <= max_seconds:
            return [("main", max(min_main, total))]

        # Minimum number of cuts to keep each <= 15s.
        cut_count = (total + max_seconds - 1) // max_seconds

        # Make at least one main cut.
        # Start with an even split, then enforce minima.
        base = total // cut_count
        rem = total % cut_count
        durs = [(base + (1 if i < rem else 0)) for i in range(cut_count)]

        # Ensure a main cut >= 5s (pick the longest).
        main_idx = max(range(len(durs)), key=lambda i: durs[i])
        if durs[main_idx] < min_main:
            needed = min_main - durs[main_idx]
            durs[main_idx] += needed
            for i in range(len(durs)):
                if i == main_idx:
                    continue
                take = min(needed, max(0, durs[i] - min_sub))
                durs[i] -= take
                needed -= take
                if needed <= 0:
                    break

        # Ensure sub cuts >= 3s (best-effort). If violated, collapse into fewer cuts.
        if any(i != main_idx and d < min_sub for i, d in enumerate(durs)):
            # Fallback: use the minimal feasible cut count given min_sub and max_seconds.
            # We guarantee <= 15 by construction; we just reduce count until all subs >= 3.
            for count in range(max(2, cut_count - 1), 1, -1):
                base2 = total // count
                rem2 = total % count
                durs2 = [(base2 + (1 if i < rem2 else 0)) for i in range(count)]
                main2 = max(range(len(durs2)), key=lambda i: durs2[i])
                if durs2[main2] < min_main:
                    continue
                if all(i == main2 or d >= min_sub for i, d in enumerate(durs2)):
                    durs = durs2
                    main_idx = main2
                    break

        plan: list[tuple[str, int]] = []
        for i, d in enumerate(durs):
            role = "main" if i == main_idx else "sub"
            plan.append((role, max(1, int(d))))
        return plan

    cut_plan = plan_cut_durations(target_seconds)
    cut_count = len(cut_plan)

    lines = [
        "# シーン動画マニフェスト（DRAFT）",
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
        "    cuts:",
    ]
    for idx, (role, dur) in enumerate(cut_plan, start=1):
        # NOTE: narration.text is sent to TTS as-is. Keep it empty so missing narration is caught early.
        cut_narration_text = ""
        lines += [
            f"      - cut_id: {idx}",
            f'        cut_role: "{role}"',
            "        image_generation:",
            '          tool: "google_nanobanana_2"',
            "          character_ids: []",
            "          character_variant_ids: []",
            "          object_ids: []",
            "          object_variant_ids: []",
            "          prompt: |",
        ]
        lines += ["            " + ln for ln in image_prompt.rstrip().splitlines()]
        lines += [
            f'          output: "assets/scenes/scene{scene_id}_cut{idx}_base.png"',
            "          iterations: 4",
            "          selected: null",
            "        video_generation:",
            f'          tool: "{video_tool}"',
            f"          duration_seconds: {dur}",
            f'          input_image: "assets/scenes/scene{scene_id}_cut{idx}_base.png"',
            f'          motion_prompt: "{motion_prompt}"',
            f'          output: "assets/scenes/scene{scene_id}_cut{idx}_video.mp4"',
            "        audio:",
            "          narration:",
            f'            text: "{cut_narration_text}"',
            '            tool: "elevenlabs"',
            f'            output: "assets/audio/scene{scene_id}_cut{idx}_narration.mp3"',
            "            normalize_to_scene_duration: false",
        ]

    lines += [
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
        choices=["kling", "kling-omni", "seedance", "veo"],
        default="kling-omni",
        help='Video generation tool in manifests ("kling"=kling_3_0, "kling-omni"=kling_3_0_omni, "seedance"=seedance). "veo" is mapped to Kling for safety.',
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
    elif args.video_tool == "seedance":
        video_tool = "seedance"
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
                "gate.video_review": "required",
            },
        )

    write_text(run_dir / "research.md", "# リサーチ（出力）\n\nTODO\n", force=False)
    write_text(run_dir / "story.md", "# 物語（story）\n\nTODO\n", force=False)

    source_script = run_dir / "script.md"
    source_story = run_dir / "story.md"

    # Hybridization approval gate (human required).
    # If story/script indicates a hybridization proposal pending approval, stop here.
    story_md = source_story.read_text(encoding="utf-8") if source_story.exists() else ""
    script_md = source_script.read_text(encoding="utf-8") if source_script.exists() else ""
    hybrid_pending = detect_hybridization_pending(script_md) or detect_hybridization_pending(story_md)
    if hybrid_pending:
        state = parse_state_file(state_path)
        status = state.get("review.hybridization.status", "").strip().lower()
        if status != "approved":
            append_state_block(
                state_path,
                {
                    "timestamp": now_iso(),
                    "topic": topic_raw,
                    "status": "STORY",
                    "runtime.stage": "hybridization_review",
                    "gate.hybridization_review": "required",
                    "review.hybridization.status": "pending",
                },
            )
            print("Hybridization approval is required before scaffolding scene-series.")
            print(f"Run dir: {run_dir}")
            print("Approve (or reject) after reviewing story/script:")
            print(f'  python scripts/toc-state.py approve-hybridization --run-dir "{run_dir}" --note "OK"')
            print(f'  python scripts/toc-state.py reject-hybridization --run-dir "{run_dir}" --note "NG"')
            raise SystemExit(2)

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
                video_tool=video_tool,
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
