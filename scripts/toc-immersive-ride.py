#!/usr/bin/env python3
"""
Scaffold a run folder for the immersive (cinematic) workflow (/toc-immersive-ride).

This script is intentionally a helper:
- It creates output/<topic>_<timestamp>/ with standard files and folders
- It writes a draft video_manifest.md based on an experience-specific template in workflow/
- It does NOT call external generation APIs
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import resolve_review_policy, review_policy_state_entries, run_stage_grounding
from toc.harness import append_state_snapshot
from toc.review_loop import (
    REVIEW_LOOP_CRITIC_COUNT,
    aggregator_prompt_relpath,
    critic_prompt_relpath,
    loop_state_updates,
    render_aggregator_prompt,
    render_critic_prompt,
)

EXPERIENCE_TEMPLATES: dict[str, Path] = {
    "cinematic_story": Path("workflow/immersive-ride-video-manifest-template.md"),
    "cloud_island_walk": Path("workflow/immersive-cloud-island-walk-video-manifest-template.md"),
    # legacy alias (kept for backward compatibility; canonicalized to cinematic_story)
    "ride_action_boat": Path("workflow/immersive-ride-video-manifest-template.md"),
}
SCENE_CONTE_TEMPLATE = Path("workflow/scene-conte-template.md")
VISUAL_VALUE_TEMPLATE = Path("workflow/visual-value-template.yaml")

BIG_STAGE_HANDOFF_SLOTS: dict[str, str] = {
    "p100": "p130",
    "p200": "p230",
    "p300": "p330",
    "p400": "p450",
    "p500": "p570",
    "p600": "p680",
    "p700": "p750",
    "p800": "p850",
    "p900": "p930",
}

STAGE_TARGETS: dict[str, str] = {
    "100": "p130",
    "p100": "p130",
    "research": "p130",
    "200": "p230",
    "p200": "p230",
    "story": "p230",
    "300": "p330",
    "p300": "p330",
    "visual": "p330",
    "visual_value": "p330",
    "400": "p450",
    "p400": "p450",
    "450": "p450",
    "p450": "p450",
    "script": "p450",
    "500": "p570",
    "p500": "p570",
    "narration": "p570",
}
for _big_stage, _handoff_slot in BIG_STAGE_HANDOFF_SLOTS.items():
    STAGE_TARGETS.setdefault(_big_stage, _handoff_slot)
    STAGE_TARGETS.setdefault(_big_stage.removeprefix("p"), _handoff_slot)
for _slot_number in range(110, 931, 10):
    STAGE_TARGETS.setdefault(str(_slot_number), f"p{_slot_number}")
    STAGE_TARGETS.setdefault(f"p{_slot_number}", f"p{_slot_number}")

SCAFFOLD_AUTHORING_UPDATES: dict[str, dict[str, str]] = {
    "research": {
        "stage.research.status": "pending",
        "artifact.research.status": "scaffold",
        "slot.p120.status": "pending",
        "slot.p120.note": "scaffold placeholder; author research.md before marking done",
    },
    "story": {
        "stage.story.status": "pending",
        "artifact.story.status": "scaffold",
        "slot.p220.status": "pending",
        "slot.p220.note": "scaffold placeholder; author story.md before marking done",
    },
    "visual_value": {
        "stage.visual_value.status": "pending",
        "artifact.visual_value.status": "scaffold",
        "slot.p310.status": "pending",
        "slot.p310.note": "scaffold template; replace placeholders before marking done",
    },
    "script": {
        "stage.script.status": "pending",
        "artifact.script.status": "scaffold",
        "slot.p420.status": "pending",
        "slot.p420.note": "scaffold placeholder; author script.md before marking done",
    },
    "narration": {
        "stage.narration.status": "pending",
        "runtime.scaffold.narration_status": "pending",
        "runtime.scaffold.audio_status": "pending",
        "slot.p510.status": "pending",
        "slot.p510.note": "scaffold grounding only; author narration runtime handoff before marking done",
        "slot.p530.status": "pending",
        "slot.p530.note": "scaffold audio directory only; generate narration audio before marking done",
    },
    "asset": {
        "stage.asset.status": "pending",
        "artifact.asset_plan.status": "scaffold",
        "slot.p630.status": "pending",
        "slot.p630.note": "scaffold placeholder; author asset_plan.md before marking done",
        "slot.p660.status": "pending",
        "slot.p660.note": "scaffold placeholder; materialize asset requests before generation",
        "slot.p670.status": "pending",
        "slot.p670.note": "scaffold only; reusable asset generation has not run",
    },
    "scene_implementation": {
        "stage.scene_implementation.status": "pending",
        "slot.p720.status": "pending",
        "slot.p720.note": "skeleton manifest only; production cut prompts are not authored",
    },
    "video_generation": {
        "stage.video_generation.status": "pending",
        "slot.p830.status": "pending",
        "slot.p830.note": "scaffold placeholder; video generation requests are not frozen",
        "slot.p840.status": "pending",
        "slot.p840.note": "scaffold only; video generation has not run",
    },
    "qa": {
        "stage.qa.status": "pending",
        "slot.p910.status": "pending",
        "slot.p910.note": "scaffold placeholder; render inputs are not frozen",
        "slot.p920.status": "pending",
        "slot.p920.note": "scaffold only; final render has not run",
    },
}

REVIEW_HANDOFF_UPDATES: dict[str, dict[str, str]] = {
    "research": {
        "stage.research.status": "awaiting_approval",
        "review.research.status": "pending",
        "gate.research_review": "required",
        "slot.p130.status": "pending",
        "slot.p130.note": "human review handoff; run evaluator-improvement loop before approval when required",
    },
    "story": {
        "stage.story.status": "awaiting_approval",
        "review.story.status": "pending",
        "gate.story_review": "required",
        "slot.p230.status": "pending",
        "slot.p230.note": "human review handoff; run evaluator-improvement loop before approval when required",
    },
    "visual_value": {
        "stage.visual_value.status": "awaiting_approval",
        "review.visual_value.status": "pending",
        "gate.visual_value_review": "required",
        "slot.p320.status": "pending",
        "slot.p320.note": "visual planning evaluator-improvement loop prompts are ready for critic review",
        "slot.p330.status": "pending",
        "slot.p330.note": "visual planning handoff ready for human review",
    },
    "script": {
        "stage.script.status": "awaiting_approval",
        "review.script.status": "pending",
        "gate.script_review": "required",
        "slot.p430.status": "pending",
        "slot.p430.note": "human review handoff; run evaluator-improvement loop before approval when required",
    },
    "narration": {
        "stage.narration.status": "awaiting_approval",
        "review.narration.status": "pending",
        "gate.narration_review": "required",
        "slot.p570.status": "pending",
        "slot.p570.note": "audio QA / human review handoff scaffolded; generate audio before final approval when required",
    },
    "asset": {
        "stage.asset.status": "awaiting_approval",
        "review.asset.status": "pending",
        "gate.asset_review": "required",
        "slot.p640.status": "pending",
        "slot.p640.note": "asset evaluator-improvement loop prompts are ready for critic review",
        "slot.p680.status": "pending",
        "slot.p680.note": "asset continuity handoff ready for human review",
    },
    "scene_implementation": {
        "stage.scene_implementation.status": "awaiting_approval",
        "review.image_prompt.status": "pending",
        "review.image_prompt.judgment.status": "pending",
        "gate.image_prompt_review": "required",
        "slot.p730.status": "pending",
        "slot.p730.note": "hard scene evaluator-improvement loop prompts are ready for critic review",
        "slot.p740.status": "pending",
        "slot.p740.note": "judgment evaluator-improvement loop prompts are ready for critic review",
        "slot.p750.status": "pending",
        "slot.p750.note": "generation-ready handoff ready for human review",
    },
    "video_generation": {
        "stage.video_generation.status": "awaiting_approval",
        "review.video.status": "pending",
        "gate.video_review": "required",
        "slot.p820.status": "pending",
        "slot.p820.note": "motion/video evaluator-improvement loop prompts are ready for critic review",
        "slot.p850.status": "pending",
        "slot.p850.note": "video review/exclusion handoff ready for human review",
    },
    "qa": {
        "stage.qa.status": "awaiting_approval",
        "review.video.status": "pending",
        "gate.video_review": "required",
        "slot.p930.status": "pending",
        "slot.p930.note": "QA/runtime summary handoff ready for final human review",
    },
}


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


def append_state_block(state_path: Path, kv: dict[str, str]) -> None:
    append_state_snapshot(state_path, kv)


def write_text(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def maybe_run_stage_grounding(run_dir: Path, stage: str, *, flow: str) -> None:
    run_stage_grounding(run_dir, stage, flow=flow, retries=1)


def ensure_skeleton_manifest(manifest_text: str) -> str:
    if "manifest_phase:" in manifest_text:
        return manifest_text
    return manifest_text.replace("```yaml\n", "```yaml\nmanifest_phase: skeleton\n", 1)


def normalize_stage_target(value: str) -> str:
    key = value.strip().lower().removeprefix("--stage=").replace("-", "_")
    if key not in STAGE_TARGETS:
        allowed = ", ".join(sorted(STAGE_TARGETS))
        raise argparse.ArgumentTypeError(f"unknown stage target: {value!r}; expected one of {allowed}")
    return STAGE_TARGETS[key]


def slot_number(slot: str) -> int:
    return int(slot.removeprefix("p"))


def slot_bucket(slot: str) -> str:
    number = slot_number(slot)
    return f"p{number // 100}00"


def target_reaches(stop_slot: str, slot: str) -> bool:
    return slot_number(stop_slot) >= slot_number(slot)


def review_handoff_updates(*stage_names: str) -> dict[str, str]:
    updates: dict[str, str] = {}
    for stage_name in stage_names:
        updates.update(REVIEW_HANDOFF_UPDATES[stage_name])
    return updates


def materialize_review_loop_prompts(run_dir: Path, *, stage: str, round_number: int = 1) -> dict[str, str]:
    updates = loop_state_updates(stage=stage, status="pending", current_round=0)
    for idx in range(1, REVIEW_LOOP_CRITIC_COUNT + 1):
        prompt_rel = critic_prompt_relpath(stage, round_number, idx)
        prompt_path = run_dir / prompt_rel
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            render_critic_prompt(run_dir=run_dir.resolve(), stage=stage, round_number=round_number, critic_number=idx) + "\n",
            encoding="utf-8",
        )
        updates[f"eval.{stage}.loop.round_{round_number:02d}.critic_{idx}_prompt"] = str(prompt_rel)
    aggregate_prompt_rel = aggregator_prompt_relpath(stage, round_number)
    aggregate_prompt_path = run_dir / aggregate_prompt_rel
    aggregate_prompt_path.parent.mkdir(parents=True, exist_ok=True)
    aggregate_prompt_path.write_text(
        render_aggregator_prompt(run_dir=run_dir.resolve(), stage=stage, round_number=round_number) + "\n",
        encoding="utf-8",
    )
    updates[f"eval.{stage}.loop.round_{round_number:02d}.aggregator_prompt"] = str(aggregate_prompt_rel)
    return updates


def merge_review_loop_updates(run_dir: Path, *stage_names: str) -> dict[str, str]:
    updates: dict[str, str] = {}
    for stage_name in stage_names:
        updates.update(materialize_review_loop_prompts(run_dir, stage=stage_name))
    return updates


def finish_scaffold(
    state_path: Path,
    topic: str,
    run_dir: Path,
    stop_slot: str,
    updates: dict[str, str] | None = None,
    *,
    legacy_done: bool = False,
) -> None:
    if legacy_done:
        payload = {
            "timestamp": now_iso(),
            "topic": topic,
            "status": "DONE",
            "runtime.stage": "immersive_ride_scaffolded",
        }
    else:
        stage_target = slot_bucket(stop_slot)
        payload = {
            "timestamp": now_iso(),
            "topic": topic,
            "status": stage_target.upper(),
            "runtime.stage": f"immersive_ride_scaffolded_{stop_slot}",
            "runtime.stage_target": stage_target,
            "runtime.stop_slot": stop_slot,
        }
    if updates:
        payload.update(updates)
    append_state_block(state_path, payload)
    print(f"Run dir: {run_dir.resolve()}")


def scaffold_authoring_updates(*stage_names: str) -> dict[str, str]:
    updates = {
        "runtime.scaffold.status": "draft",
        "runtime.scaffold.content_status": "placeholder",
    }
    for stage_name in stage_names:
        updates.update(SCAFFOLD_AUTHORING_UPDATES[stage_name])
    return updates


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold an immersive run folder.")
    parser.add_argument("--topic", required=True, help="Video topic (used for folder name).")
    parser.add_argument("--timestamp", default=None, help="Timestamp (YYYYMMDD_HHMM).")
    parser.add_argument("--base", default="output", help="Base output directory.")
    parser.add_argument("--run-dir", default=None, help="Override run directory path.")
    parser.add_argument(
        "--stage",
        type=normalize_stage_target,
        default=None,
        help="Stop target. Coarse p100/100-style targets stop at that stage's human-review handoff slot; fine slots stop exactly.",
    )
    parser.add_argument(
        "--experience",
        choices=sorted(EXPERIENCE_TEMPLATES.keys()),
        default="cloud_island_walk",
        help="Experience template to scaffold (default: cloud_island_walk).",
    )
    parser.add_argument(
        "--video-tool",
        choices=["kling", "kling-omni", "seedance", "veo"],
        default="kling-omni",
        help='Video generation tool in manifest ("kling", "kling-omni", or "seedance"). "veo" is mapped to Kling for safety.',
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing files.")
    parser.add_argument("--review-policy", choices=["strict", "drafts"], default="strict")
    parser.add_argument("--story-review", choices=["required", "optional"], default=None)
    parser.add_argument("--image-review", choices=["required", "optional"], default=None)
    parser.add_argument("--narration-review", choices=["required", "optional"], default=None)
    args = parser.parse_args()
    stop_slot = args.stage or "p570"
    legacy_default = args.stage is None

    topic_raw = args.topic
    topic_slug = sanitize_topic(topic_raw)
    ts = args.timestamp or default_timestamp()

    experience = str(args.experience)
    if experience == "ride_action_boat":
        print("[warn] --experience ride_action_boat is deprecated; using cinematic_story.")
        experience = "cinematic_story"

    run_dir = Path(args.run_dir) if args.run_dir else (Path(args.base) / f"{topic_slug}_{ts}")
    run_dir.mkdir(parents=True, exist_ok=True)
    review_policy = resolve_review_policy(
        preset=args.review_policy,
        story_review=args.story_review,
        image_review=args.image_review,
        narration_review=args.narration_review,
    )

    # assets
    (run_dir / "assets" / "characters").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "objects").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "styles").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "scenes").mkdir(parents=True, exist_ok=True)
    (run_dir / "assets" / "audio").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs" / "grounding").mkdir(parents=True, exist_ok=True)

    state_path = run_dir / "state.txt"
    if not state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "topic": topic_raw,
                "status": "INIT",
                "runtime.stage": "immersive_ride_scaffold",
                "gate.video_review": "required",
                "immersive.experience": str(experience),
                "runtime.review_policy": args.review_policy,
                **review_policy_state_entries(review_policy),
            },
        )

    write_text(run_dir / "research.md", "# リサーチ（出力）\n\nTODO\n", force=args.force)
    maybe_run_stage_grounding(run_dir, "research", flow="immersive")
    if not target_reaches(stop_slot, "p210"):
        review_updates = materialize_review_loop_prompts(run_dir, stage="research")
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research"),
                **review_updates,
                **review_handoff_updates("research"),
                "artifact.research": str((run_dir / "research.md").resolve()),
            },
        )
        return

    write_text(run_dir / "story.md", "# 物語（story）\n\nTODO\n", force=args.force)
    maybe_run_stage_grounding(run_dir, "story", flow="immersive")
    if not target_reaches(stop_slot, "p310"):
        review_updates = materialize_review_loop_prompts(run_dir, stage="story")
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story"),
                **review_updates,
                **review_handoff_updates("story"),
                "artifact.research": str((run_dir / "research.md").resolve()),
                "artifact.story": str((run_dir / "story.md").resolve()),
            },
        )
        return

    if VISUAL_VALUE_TEMPLATE.exists():
        visual_value = (
            VISUAL_VALUE_TEMPLATE.read_text(encoding="utf-8")
            .replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
        write_text(run_dir / "visual_value.md", visual_value, force=args.force)
    else:
        write_text(run_dir / "visual_value.md", "# 視覚化価値パート（visual value）\n\nTODO\n", force=args.force)
    maybe_run_stage_grounding(run_dir, "visual_value", flow="immersive")
    if not target_reaches(stop_slot, "p410"):
        review_updates = materialize_review_loop_prompts(run_dir, stage="visual_value")
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value"),
                **review_updates,
                **review_handoff_updates("visual_value"),
                "artifact.research": str((run_dir / "research.md").resolve()),
                "artifact.story": str((run_dir / "story.md").resolve()),
                "artifact.visual_value": str((run_dir / "visual_value.md").resolve()),
            },
        )
        return

    write_text(run_dir / "script.md", "# 台本（没入型 / cinematic）\n\nTODO\n", force=args.force)
    maybe_run_stage_grounding(run_dir, "script", flow="immersive")
    if not target_reaches(stop_slot, "p450"):
        review_updates = materialize_review_loop_prompts(run_dir, stage="script")
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script"),
                **review_updates,
                **review_handoff_updates("script"),
                "artifact.research": str((run_dir / "research.md").resolve()),
                "artifact.story": str((run_dir / "story.md").resolve()),
                "artifact.visual_value": str((run_dir / "visual_value.md").resolve()),
                "artifact.script": str((run_dir / "script.md").resolve()),
            },
        )
        return

    if SCENE_CONTE_TEMPLATE.exists():
        tmpl = SCENE_CONTE_TEMPLATE.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
        write_text(run_dir / "scene_conte.md", tmpl, force=args.force)

    template_path = EXPERIENCE_TEMPLATES.get(str(experience))
    if template_path is None:
        raise SystemExit(f"Unknown --experience: {experience}")
    if template_path.exists():
        tmpl = template_path.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
        )
        if args.video_tool == "kling":
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "kling_3_0"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0_omni"\s*$', r'\1tool: "kling_3_0"', tmpl)
        elif args.video_tool == "seedance":
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "seedance"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0"\s*$', r'\1tool: "seedance"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0_omni"\s*$', r'\1tool: "seedance"', tmpl)
        elif args.video_tool in {"kling-omni", "veo"}:
            if args.video_tool == "veo":
                print('[warn] --video-tool veo is disabled for safety; using kling_3_0_omni instead.')
            tmpl = re.sub(r'(?m)^(\s*)tool: "google_veo_3_1"\s*$', r'\1tool: "kling_3_0_omni"', tmpl)
            tmpl = re.sub(r'(?m)^(\s*)tool: "kling_3_0"\s*$', r'\1tool: "kling_3_0_omni"', tmpl)
        write_text(run_dir / "video_manifest.md", ensure_skeleton_manifest(tmpl), force=args.force)
    else:
        write_text(run_dir / "video_manifest.md", "```yaml\nmanifest_phase: skeleton\nvideo_metadata:\n  topic: \"<topic>\"\nscenes: []\n```\n", force=args.force)

    if not target_reaches(stop_slot, "p510"):
        review_updates = materialize_review_loop_prompts(run_dir, stage="script")
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script"),
                **review_updates,
                **review_handoff_updates("script"),
                "immersive.experience": str(experience),
                "artifact.research": str((run_dir / "research.md").resolve()),
                "artifact.story": str((run_dir / "story.md").resolve()),
                "artifact.visual_value": str((run_dir / "visual_value.md").resolve()),
                "artifact.script": str((run_dir / "script.md").resolve()),
                "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
            },
        )
        return

    maybe_run_stage_grounding(run_dir, "narration", flow="immersive")
    review_updates = materialize_review_loop_prompts(run_dir, stage="narration")
    common_artifacts = {
        "immersive.experience": str(experience),
        "artifact.research": str((run_dir / "research.md").resolve()),
        "artifact.story": str((run_dir / "story.md").resolve()),
        "artifact.visual_value": str((run_dir / "visual_value.md").resolve()),
        "artifact.script": str((run_dir / "script.md").resolve()),
        "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
    }

    if not target_reaches(stop_slot, "p610"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration"),
                **review_updates,
                **review_handoff_updates("narration"),
                **common_artifacts,
            },
            legacy_done=legacy_default,
        )
        return

    write_text(run_dir / "asset_plan.md", "# Asset Plan\n\nTODO\n", force=args.force)
    write_text(run_dir / "asset_generation_requests.md", "# Asset Generation Requests\n\nTODO\n", force=args.force)
    write_text(run_dir / "asset_generation_manifest.md", "```yaml\nassets: []\n```\n", force=args.force)
    asset_review_updates = merge_review_loop_updates(run_dir, "asset")
    asset_artifacts = {
        "artifact.asset_plan": str((run_dir / "asset_plan.md").resolve()),
        "artifact.asset_generation_requests": str((run_dir / "asset_generation_requests.md").resolve()),
        "artifact.asset_generation_manifest": str((run_dir / "asset_generation_manifest.md").resolve()),
    }
    if not target_reaches(stop_slot, "p710"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration", "asset"),
                **review_updates,
                **asset_review_updates,
                **review_handoff_updates("asset"),
                **common_artifacts,
                **asset_artifacts,
            },
        )
        return

    write_text(run_dir / "image_prompt_story_review.md", "# Image Prompt Story Review\n\nTODO\n", force=args.force)
    write_text(run_dir / "image_generation_requests.md", "# Image Generation Requests\n\nTODO\n", force=args.force)
    scene_review_updates = merge_review_loop_updates(
        run_dir,
        "scene_implementation_hard",
        "scene_implementation_judgment",
    )
    scene_artifacts = {
        "artifact.image_prompt_story_review": str((run_dir / "image_prompt_story_review.md").resolve()),
        "artifact.image_generation_requests": str((run_dir / "image_generation_requests.md").resolve()),
    }
    if not target_reaches(stop_slot, "p810"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration", "asset", "scene_implementation"),
                **review_updates,
                **asset_review_updates,
                **scene_review_updates,
                **review_handoff_updates("scene_implementation"),
                **common_artifacts,
                **asset_artifacts,
                **scene_artifacts,
            },
        )
        return

    write_text(run_dir / "video_generation_requests.md", "# Video Generation Requests\n\nTODO\n", force=args.force)
    video_review_updates = merge_review_loop_updates(run_dir, "video_generation_motion", "video_generation_review")
    video_artifacts = {
        "artifact.video_generation_requests": str((run_dir / "video_generation_requests.md").resolve()),
    }
    if not target_reaches(stop_slot, "p910"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration", "asset", "scene_implementation", "video_generation"),
                **review_updates,
                **asset_review_updates,
                **scene_review_updates,
                **video_review_updates,
                **review_handoff_updates("video_generation"),
                **common_artifacts,
                **asset_artifacts,
                **scene_artifacts,
                **video_artifacts,
            },
        )
        return

    write_text(run_dir / "run_report.md", "# Run Report\n\nTODO\n", force=args.force)
    write_text(run_dir / "eval_report.json", "{}\n", force=args.force)
    qa_review_updates = merge_review_loop_updates(run_dir, "qa")
    finish_scaffold(
        state_path,
        topic_raw,
        run_dir,
        stop_slot,
        {
            **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration", "asset", "scene_implementation", "video_generation", "qa"),
            **review_updates,
            **asset_review_updates,
            **scene_review_updates,
            **video_review_updates,
            **qa_review_updates,
            **review_handoff_updates("qa"),
            **common_artifacts,
            **asset_artifacts,
            **scene_artifacts,
            **video_artifacts,
            "artifact.run_report": str((run_dir / "run_report.md").resolve()),
            "artifact.eval_report": str((run_dir / "eval_report.json").resolve()),
        },
    )


if __name__ == "__main__":
    main()
