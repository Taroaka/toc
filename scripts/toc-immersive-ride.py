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
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.grounding import StageGroundingError, resolve_review_policy, review_policy_state_entries, run_stage_grounding
from toc.harness import append_state_snapshot, parse_state_file
from toc.review_loop import (
    REVIEW_LOOP_CRITIC_COUNT,
    aggregator_prompt_relpath,
    critic_prompt_relpath,
    final_review_relpath,
    loop_state_updates,
    render_aggregator_prompt,
    render_critic_prompt,
    review_input_snapshot_issues,
)
from toc.review_loop_runner import materialize_review_loop_round
from toc.stage_evaluator import check_manifest_single
from scripts.world_walk_source import validate_world_walk_source_path

EXPERIENCE_TEMPLATES: dict[str, Path] = {
    "cinematic_story": Path("workflow/immersive-ride-video-manifest-template.md"),
    "cloud_island_walk": Path("workflow/immersive-cloud-island-walk-video-manifest-template.md"),
    "world_walk": Path("workflow/immersive-world-walk-video-manifest-template.md"),
    # legacy alias (kept for backward compatibility; canonicalized to cinematic_story)
    "ride_action_boat": Path("workflow/immersive-ride-video-manifest-template.md"),
}
SCENE_CONTE_TEMPLATE = Path("workflow/scene-conte-template.md")
VISUAL_VALUE_TEMPLATE = Path("workflow/visual-value-template.yaml")
P400_REVIEW_STAGES = (
    "scene_set",
    "scene_detail",
    "cut_blueprint",
    "script",
    "production_readiness",
)

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
    "asset": "p570",
    "600": "p680",
    "p600": "p680",
    "image": "p680",
    "image_generation": "p680",
    "scene_implementation": "p680",
    "700": "p750",
    "p700": "p750",
    "narration": "p750",
    "800": "p850",
    "p800": "p850",
    "video_generation": "p850",
}
for _big_stage, _handoff_slot in BIG_STAGE_HANDOFF_SLOTS.items():
    STAGE_TARGETS.setdefault(_big_stage, _handoff_slot)
    STAGE_TARGETS.setdefault(_big_stage.removeprefix("p"), _handoff_slot)
for _slot_number in range(110, 931, 10):
    STAGE_TARGETS.setdefault(str(_slot_number), f"p{_slot_number}")
    STAGE_TARGETS.setdefault(f"p{_slot_number}", f"p{_slot_number}")
STAGE_TARGETS.setdefault("435", "p435")
STAGE_TARGETS.setdefault("p435", "p435")

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
        "review.script.scene_set.status": "pending",
        "review.script.scene_detail.status": "pending",
        "review.script.cut.status": "pending",
        "review.script.production_readiness.status": "pending",
        "gate.script_scene_review": "optional",
        "gate.script_cut_review": "optional",
        "gate.script_production_readiness_review": "optional",
        "eval.scene_set.loop.status": "pending",
        "eval.scene_detail.loop.status": "pending",
        "eval.cut_blueprint.loop.status": "pending",
        "eval.production_readiness.loop.status": "pending",
        "slot.p410.status": "pending",
        "slot.p410.note": "scene completion gate; abstract scene-set review must pass before concrete per-scene review and cut authoring",
        "slot.p420.status": "pending",
        "slot.p420.note": "cut blueprint authoring waits until all scenes pass p410 gates",
        "slot.p435.status": "pending",
        "slot.p435.note": "production readiness council; advisory agents report and only the Design Owner applies downstream design changes",
        "slot.p450.status": "pending",
        "slot.p450.note": "review-bound skeleton exists; p450 readiness handoff remains pending before p500",
    },
    "narration": {
        "stage.narration.status": "pending",
        "runtime.scaffold.narration_status": "pending",
        "runtime.scaffold.audio_status": "pending",
        "slot.p710.status": "pending",
        "slot.p710.note": "scaffold grounding only; author narration runtime handoff before marking done",
        "slot.p730.status": "pending",
        "slot.p730.note": "scaffold audio directory only; generate narration audio before marking done",
    },
    "asset": {
        "stage.asset.status": "pending",
        "artifact.asset_inventory.status": "scaffold",
        "artifact.asset_plan.status": "scaffold",
        "slot.p510.status": "pending",
        "slot.p510.note": "scaffold grounding only; resolve asset stage context before marking done",
        "slot.p520.status": "pending",
        "slot.p520.note": "scaffold placeholder; inventory reusable characters, objects, locations, setpieces, and stills before asset planning",
        "slot.p530.status": "pending",
        "slot.p530.note": "scaffold placeholder; author asset_plan.md before marking done",
        "slot.p550.status": "pending",
        "slot.p550.note": "scaffold placeholder; materialize asset requests before generation",
        "slot.p560.status": "pending",
        "slot.p560.note": "scaffold only; reusable asset generation has not run",
    },
    "scene_implementation": {
        "stage.scene_implementation.status": "pending",
        "slot.p620.status": "pending",
        "slot.p620.note": "skeleton manifest only; production cut prompts are not authored",
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
        "review.script.scene_set.status": "pending",
        "review.script.scene_detail.status": "pending",
        "review.script.cut.status": "pending",
        "review.script.production_readiness.status": "pending",
        "gate.script_review": "required",
        "gate.script_scene_review": "optional",
        "gate.script_cut_review": "optional",
        "gate.script_production_readiness_review": "optional",
        "slot.p430.status": "pending",
        "slot.p430.note": "human review handoff; run evaluator-improvement loop before approval when required",
        "slot.p435.status": "pending",
        "slot.p435.note": "production readiness council; advisory agents report and only the Design Owner applies downstream design changes",
        "slot.p450.status": "pending",
        "slot.p450.note": "review-bound skeleton exists; p450 readiness handoff remains pending before p500",
    },
    "narration": {
        "stage.narration.status": "awaiting_approval",
        "review.narration.status": "pending",
        "gate.narration_review": "required",
        "slot.p750.status": "pending",
        "slot.p750.note": "audio QA / human review handoff scaffolded; generate audio before final approval when required",
    },
    "asset": {
        "stage.asset.status": "awaiting_approval",
        "review.asset.status": "pending",
        "gate.asset_review": "required",
        "slot.p540.status": "pending",
        "slot.p540.note": "asset evaluator-improvement loop prompts are ready for critic review",
        "slot.p570.status": "pending",
        "slot.p570.note": "asset continuity handoff ready for human review",
    },
    "scene_implementation": {
        "stage.scene_implementation.status": "awaiting_approval",
        "review.image_prompt.status": "pending",
        "review.image_prompt.judgment.status": "pending",
        "gate.image_prompt_review": "required",
        "slot.p630.status": "pending",
        "slot.p630.note": "hard scene evaluator-improvement loop prompts are ready for critic review",
        "slot.p640.status": "pending",
        "slot.p640.note": "judgment evaluator-improvement loop prompts are ready for critic review",
        "slot.p680.status": "pending",
        "slot.p680.note": "image generation handoff ready for human review before narration",
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


def maybe_run_stage_grounding(run_dir: Path, stage: str, *, flow: str, fatal: bool = True) -> None:
    try:
        run_stage_grounding(run_dir, stage, flow=flow, retries=1)
    except StageGroundingError:
        if fatal:
            raise


def require_fresh_p400_readiness(run_dir: Path) -> None:
    _stage_result, updates = check_manifest_single(run_dir, "standard", "immersive")
    append_state_snapshot(run_dir / "state.txt", updates)
    if updates.get("eval.p400_readiness.status") != "approved":
        reasons = updates.get("eval.p400_readiness.reason_keys") or "unknown"
        raise SystemExit(f"p400 readiness gate is not approved: {reasons}")


def ensure_skeleton_manifest(manifest_text: str) -> str:
    if "manifest_phase:" in manifest_text:
        return re.sub(r"(?m)^(\s*manifest_phase:\s*).*$", r"\1skeleton", manifest_text, count=1)
    return manifest_text.replace("```yaml\n", "```yaml\nmanifest_phase: skeleton\n", 1)


def ensure_skeleton_manifest_file(manifest_path: Path) -> None:
    if not manifest_path.exists():
        return
    text = manifest_path.read_text(encoding="utf-8")
    updated = ensure_skeleton_manifest(text)
    if updated != text:
        manifest_path.write_text(updated, encoding="utf-8")


def ensure_production_manifest_file(manifest_path: Path) -> None:
    if not manifest_path.exists():
        return
    text = manifest_path.read_text(encoding="utf-8")
    if "manifest_phase:" in text:
        updated = re.sub(r"(?m)^(\s*manifest_phase:\s*).*$", r"\1production", text, count=1)
    else:
        updated = text.replace("```yaml\n", "```yaml\nmanifest_phase: production\n", 1)
    if updated != text:
        manifest_path.write_text(updated, encoding="utf-8")


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
    return materialize_review_loop_round(
        run_dir=run_dir,
        stage=stage,
        round_number=round_number,
    )


def merge_review_loop_updates(run_dir: Path, *stage_names: str) -> dict[str, str]:
    updates: dict[str, str] = {}
    for stage_name in stage_names:
        updates.update(materialize_review_loop_prompts(run_dir, stage=stage_name))
    return updates


def p400_review_stages_for_stop(stop_slot: str) -> tuple[str, ...]:
    stages: list[str] = ["scene_set", "scene_detail"]
    if target_reaches(stop_slot, "p420"):
        stages.append("cut_blueprint")
    if target_reaches(stop_slot, "p430"):
        stages.append("script")
    if target_reaches(stop_slot, "p435"):
        stages.append("production_readiness")
    return tuple(stages)


def previous_stop_slot(state: dict[str, str]) -> str | None:
    raw = str(state.get("runtime.stop_slot") or "").strip().lower()
    return raw if re.fullmatch(r"p\d{3}", raw) else None


def is_genuine_rewind(state: dict[str, str], stop_slot: str) -> bool:
    previous = previous_stop_slot(state)
    return previous is not None and slot_number(stop_slot) < slot_number(previous)


def review_round_number(state: dict[str, str], stage: str) -> int:
    raw = str(state.get(f"eval.{stage}.loop.current_round") or "").strip()
    try:
        round_number = int(raw)
    except ValueError:
        return 0
    return round_number if round_number > 0 else 0


def p400_review_is_current(run_dir: Path, state: dict[str, str], stage: str) -> bool:
    round_number = review_round_number(state, stage)
    if round_number == 0:
        return False
    if review_input_snapshot_issues(
        run_dir=run_dir,
        stage=stage,
        round_number=round_number,
    ):
        return False
    loop_status = str(state.get(f"eval.{stage}.loop.status") or "").strip().lower()
    if loop_status in {"passed", "approved", "complete", "completed", "done"}:
        return (run_dir / final_review_relpath(stage)).is_file()
    return True


def p400_review_inputs_changed(run_dir: Path, state: dict[str, str]) -> bool:
    for stage in P400_REVIEW_STAGES:
        round_number = review_round_number(state, stage)
        if round_number == 0:
            continue
        if review_input_snapshot_issues(
            run_dir=run_dir,
            stage=stage,
            round_number=round_number,
        ):
            return True
        loop_status = str(state.get(f"eval.{stage}.loop.status") or "").strip().lower()
        if loop_status in {"passed", "approved", "complete", "completed", "done"}:
            if not (run_dir / final_review_relpath(stage)).is_file():
                return True
    return False


def merge_current_or_materialized_p400_reviews(
    run_dir: Path,
    *stage_names: str,
) -> tuple[dict[str, str], tuple[str, ...]]:
    state = parse_state_file(run_dir / "state.txt")
    updates: dict[str, str] = {}
    reused: list[str] = []
    for stage_name in stage_names:
        if p400_review_is_current(run_dir, state, stage_name):
            reused.append(stage_name)
            continue
        updates.update(materialize_review_loop_prompts(run_dir, stage=stage_name))
    return updates, tuple(reused)


def preserved_p400_state_updates(
    state: dict[str, str],
    reused_stages: tuple[str, ...],
) -> dict[str, str]:
    reused = set(reused_stages)
    updates: dict[str, str] = {}
    review_status_keys = {
        "scene_set": "review.script.scene_set.status",
        "scene_detail": "review.script.scene_detail.status",
        "cut_blueprint": "review.script.cut.status",
        "script": "review.script.status",
        "production_readiness": "review.script.production_readiness.status",
    }
    for stage in reused:
        prefix = f"eval.{stage}.loop."
        updates.update({key: value for key, value in state.items() if key.startswith(prefix)})
        status_key = review_status_keys[stage]
        if status_key in state:
            updates[status_key] = state[status_key]

    if {"scene_set", "scene_detail"}.issubset(reused) and "slot.p410.status" in state:
        updates["slot.p410.status"] = state["slot.p410.status"]
    for stage, slot in (
        ("cut_blueprint", "p420"),
        ("script", "p430"),
        ("production_readiness", "p435"),
    ):
        if stage in reused and f"slot.{slot}.status" in state:
            updates[f"slot.{slot}.status"] = state[f"slot.{slot}.status"]

    if reused == set(P400_REVIEW_STAGES):
        for key in (
            "stage.script.status",
            "artifact.script.status",
            "review.script.status",
            "gate.script_review",
            "gate.script_scene_review",
            "gate.script_cut_review",
            "gate.script_production_readiness_review",
            "slot.p450.status",
            "slot.p450.note",
            "eval.p400_readiness.status",
            "eval.p400_readiness.reason_keys",
        ):
            if key in state:
                updates[key] = state[key]
    return updates


def prepare_p400_review_updates(
    run_dir: Path,
    stop_slot: str,
) -> tuple[dict[str, str], dict[str, str]]:
    review_updates, reused_stages = merge_current_or_materialized_p400_reviews(
        run_dir,
        *p400_review_stages_for_stop(stop_slot),
    )
    preservation_updates = preserved_p400_state_updates(
        parse_state_file(run_dir / "state.txt"),
        reused_stages,
    )
    return review_updates, preservation_updates


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


def reset_p400_review_handoff(
    run_dir: Path,
    *,
    experience: str,
    source_run: Path | None,
) -> dict[str, str]:
    stages = ("scene_set", "scene_detail", "cut_blueprint", "script", "production_readiness")
    updates = {
        **scaffold_authoring_updates("script"),
        **review_handoff_updates("script"),
        "immersive.experience": experience,
        "immersive.source_run": source_run.as_posix() if source_run is not None else "",
        "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
        "eval.p400_readiness.status": "changes_requested",
        "eval.p400_readiness.reason_keys": "p400.review_loop_integrity",
    }
    for stage in stages:
        review_dir = run_dir / "logs" / "eval" / stage
        if review_dir.is_symlink() or review_dir.is_file():
            review_dir.unlink()
        elif review_dir.exists():
            shutil.rmtree(review_dir)
        final_report = run_dir / final_review_relpath(stage)
        if final_report.exists() or final_report.is_symlink():
            final_report.unlink()

        updates.update(loop_state_updates(stage=stage, status="pending", current_round=0))
        round_prefix = f"eval.{stage}.loop.round_01"
        updates[f"{round_prefix}.started_at"] = ""
        updates[f"{round_prefix}.aggregated_review"] = ""
        updates[f"{round_prefix}.aggregator_prompt"] = ""
        updates[f"{round_prefix}.input_snapshot"] = ""
        updates[f"{round_prefix}.input_digest"] = ""
        for critic_number in range(1, REVIEW_LOOP_CRITIC_COUNT + 1):
            updates[f"{round_prefix}.critic_{critic_number}"] = ""
            updates[f"{round_prefix}.critic_{critic_number}_prompt"] = ""
    return updates


def main() -> None:
    parser = argparse.ArgumentParser(description="Scaffold an immersive run folder.")
    parser.add_argument("--topic", required=True, help="Video topic (used for folder name).")
    parser.add_argument("--timestamp", default=None, help="Timestamp (YYYYMMDD_HHMM).")
    parser.add_argument("--base", default="output", help="Base output directory.")
    parser.add_argument("--run-dir", default=None, help="Override run directory path.")
    parser.add_argument(
        "--source-run",
        default=None,
        help="Existing ToC run directory to reference. Required for --experience world_walk.",
    )
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
    if experience == "world_walk" and args.stage is None:
        # The world-walk template is an authored source-reference skeleton.
        # Stop at the script/manifest handoff until its p400 design is approved.
        stop_slot = "p450"
    source_run_path: Path | None = Path(args.source_run) if args.source_run else None
    if experience == "world_walk":
        if source_run_path is None:
            parser.error("--source-run is required when --experience world_walk")
        try:
            _resolved_source_run, source_run_relative = validate_world_walk_source_path(
                REPO_ROOT,
                source_run_path,
            )
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))
        source_run_path = Path(source_run_relative)

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
    state_preexisting = state_path.exists()
    prior_state = parse_state_file(state_path) if state_preexisting else {}
    genuine_rewind = state_preexisting and is_genuine_rewind(prior_state, stop_slot)
    prior_p400_inputs_changed = (
        state_preexisting
        and p400_review_inputs_changed(run_dir, prior_state)
    )
    preserve_existing_authoring_grounding = (
        state_preexisting
        and not args.force
        and not genuine_rewind
        and not prior_p400_inputs_changed
        and any(
            review_round_number(prior_state, stage) > 0
            for stage in P400_REVIEW_STAGES
        )
    )
    if not state_preexisting:
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "topic": topic_raw,
                "status": "INIT",
                "runtime.stage": "immersive_ride_scaffold",
                "gate.video_review": "required",
                "immersive.experience": str(experience),
                **({"immersive.source_run": str(source_run_path)} if source_run_path is not None else {}),
                "runtime.review_policy": args.review_policy,
                **review_policy_state_entries(review_policy),
            },
        )

    write_text(run_dir / "research.md", "# リサーチ（出力）\n\nTODO\n", force=args.force)
    if not preserve_existing_authoring_grounding:
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
    if not preserve_existing_authoring_grounding:
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
    if not preserve_existing_authoring_grounding:
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
    if not preserve_existing_authoring_grounding:
        maybe_run_stage_grounding(run_dir, "script", flow="immersive")

    template_path = EXPERIENCE_TEMPLATES.get(str(experience))
    if template_path is None:
        raise SystemExit(f"Unknown --experience: {experience}")
    if template_path.exists():
        tmpl = template_path.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
            .replace("<source_run>", source_run_path.as_posix() if source_run_path is not None else "")
            .replace("<source_story>", (source_run_path / "story.md").as_posix() if source_run_path is not None else "")
            .replace("<source_assets>", (source_run_path / "assets").as_posix() if source_run_path is not None else "")
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
    manifest_path = run_dir / "video_manifest.md"
    if genuine_rewind and not target_reaches(stop_slot, "p510"):
        ensure_skeleton_manifest_file(manifest_path)
    elif target_reaches(stop_slot, "p510"):
        # P400 approvals bind video_manifest.md. Promote before refreshing the
        # final P400 snapshots and before running the readiness gate.
        ensure_production_manifest_file(manifest_path)

    requested_source_run = source_run_path.as_posix() if source_run_path is not None else ""
    review_context_changed = state_preexisting and (
        str(prior_state.get("immersive.experience") or "") != experience
        or str(prior_state.get("immersive.source_run") or "") != requested_source_run
    )
    review_inputs_changed = (
        state_preexisting
        and p400_review_inputs_changed(run_dir, prior_state)
    )
    p400_reset = bool(
        state_preexisting
        and (genuine_rewind or review_context_changed or review_inputs_changed)
    )
    if p400_reset:
        append_state_block(
            state_path,
            reset_p400_review_handoff(
                run_dir,
                experience=experience,
                source_run=source_run_path,
            ),
        )

    if not target_reaches(stop_slot, "p450"):
        review_updates, p400_preservation_updates = prepare_p400_review_updates(
            run_dir,
            stop_slot,
        )
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
                "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
                "immersive.experience": str(experience),
                "immersive.source_run": (
                    source_run_path.as_posix()
                    if source_run_path is not None
                    else ""
                ),
                **p400_preservation_updates,
            },
        )
        return

    if SCENE_CONTE_TEMPLATE.exists():
        tmpl = SCENE_CONTE_TEMPLATE.read_text(encoding="utf-8")
        tmpl = (
            tmpl.replace("<topic>", topic_raw)
            .replace("<timestamp>", ts)
            .replace("<ISO8601>", now_iso())
            .replace("<source_run>", source_run_path.as_posix() if source_run_path is not None else "")
            .replace("<source_story>", (source_run_path / "story.md").as_posix() if source_run_path is not None else "")
            .replace("<source_assets>", (source_run_path / "assets").as_posix() if source_run_path is not None else "")
        )
        write_text(run_dir / "scene_conte.md", tmpl, force=args.force)

    if not target_reaches(stop_slot, "p510"):
        review_updates, p400_preservation_updates = prepare_p400_review_updates(
            run_dir,
            stop_slot,
        )
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
                "immersive.source_run": requested_source_run,
                **p400_preservation_updates,
            },
        )
        return

    common_artifacts = {
        "immersive.experience": str(experience),
        "immersive.source_run": requested_source_run,
        "artifact.research": str((run_dir / "research.md").resolve()),
        "artifact.story": str((run_dir / "story.md").resolve()),
        "artifact.visual_value": str((run_dir / "visual_value.md").resolve()),
        "artifact.script": str((run_dir / "script.md").resolve()),
        "artifact.video_manifest": str((run_dir / "video_manifest.md").resolve()),
    }
    p400_review_updates, p400_preservation_updates = prepare_p400_review_updates(
        run_dir,
        stop_slot,
    )

    require_fresh_p400_readiness(run_dir)
    maybe_run_stage_grounding(run_dir, "asset", flow="immersive")
    write_text(run_dir / "asset_inventory.md", "# Asset Inventory\n\nTODO\n", force=args.force)
    write_text(run_dir / "asset_plan.md", "# Asset Plan\n\nTODO\n", force=args.force)
    write_text(run_dir / "asset_generation_requests.md", "# Asset Generation Requests\n\nTODO\n", force=args.force)
    write_text(run_dir / "asset_generation_manifest.md", "```yaml\nassets: []\n```\n", force=args.force)
    asset_review_updates = merge_review_loop_updates(run_dir, "asset")
    asset_artifacts = {
        "artifact.asset_inventory": str((run_dir / "asset_inventory.md").resolve()),
        "artifact.asset_plan": str((run_dir / "asset_plan.md").resolve()),
        "artifact.asset_generation_requests": str((run_dir / "asset_generation_requests.md").resolve()),
        "artifact.asset_generation_manifest": str((run_dir / "asset_generation_manifest.md").resolve()),
    }
    if not target_reaches(stop_slot, "p610"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "asset"),
                **p400_review_updates,
                **asset_review_updates,
                **review_handoff_updates("asset"),
                **common_artifacts,
                **asset_artifacts,
                **p400_preservation_updates,
            },
            legacy_done=legacy_default,
        )
        return

    maybe_run_stage_grounding(run_dir, "scene_implementation", flow="immersive")
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
    if not target_reaches(stop_slot, "p710"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "asset", "scene_implementation"),
                **p400_review_updates,
                **asset_review_updates,
                **scene_review_updates,
                **review_handoff_updates("scene_implementation"),
                **common_artifacts,
                **asset_artifacts,
                **scene_artifacts,
                **p400_preservation_updates,
            },
        )
        return

    maybe_run_stage_grounding(run_dir, "narration", flow="immersive")
    narration_review_updates = materialize_review_loop_prompts(run_dir, stage="narration")
    if not target_reaches(stop_slot, "p810"):
        finish_scaffold(
            state_path,
            topic_raw,
            run_dir,
            stop_slot,
            {
                **scaffold_authoring_updates("research", "story", "visual_value", "script", "narration", "asset", "scene_implementation"),
                **p400_review_updates,
                **narration_review_updates,
                **asset_review_updates,
                **scene_review_updates,
                **review_handoff_updates("narration"),
                **common_artifacts,
                **asset_artifacts,
                **scene_artifacts,
                **p400_preservation_updates,
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
                **p400_review_updates,
                **narration_review_updates,
                **asset_review_updates,
                **scene_review_updates,
                **video_review_updates,
                **review_handoff_updates("video_generation"),
                **common_artifacts,
                **asset_artifacts,
                **scene_artifacts,
                **video_artifacts,
                **p400_preservation_updates,
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
            **p400_review_updates,
            **narration_review_updates,
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
            **p400_preservation_updates,
        },
    )


if __name__ == "__main__":
    main()
