#!/usr/bin/env python3
"""Prepare and optionally continue an existing frontend-created run from p500."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import append_state_snapshot, load_structured_document, parse_state_file
from toc.p500_resume import (
    P500ResumeError,
    apply_resume_plan,
    build_resume_plan,
    prepare_p500_resume,
    resolve_run_dir,
)
from toc.runtime_locks import FileLockUnavailable, sync_file_lock


def _load_frontend_runner() -> ModuleType:
    path = REPO_ROOT / "scripts" / "toc-immersive-frontend-run.py"
    spec = importlib.util.spec_from_file_location("toc_immersive_frontend_run", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load frontend runner: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _topic_for_run(run_dir: Path, explicit_topic: str) -> str:
    state_topic = str(parse_state_file(run_dir / "state.txt").get("topic") or "").strip()
    topic = explicit_topic.strip() or state_topic
    if not topic:
        _text, manifest = load_structured_document(run_dir / "video_manifest.md")
        metadata = manifest.get("video_metadata")
        if isinstance(metadata, dict):
            topic = str(metadata.get("topic") or "").strip()
    if not topic:
        raise P500ResumeError("could not resolve the existing run topic")
    if explicit_topic.strip() and state_topic and explicit_topic.strip() != state_topic:
        raise P500ResumeError(
            f"--topic does not match the existing run: {explicit_topic.strip()} != {state_topic}"
        )
    return topic


def _resume_profile(
    frontend: ModuleType,
    *,
    run_dir: Path,
    topic: str,
    source: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _manifest_text, manifest = load_structured_document(run_dir / "video_manifest.md")
    if not manifest:
        raise P500ResumeError("video_manifest.md is not a structured document")
    metadata = manifest.get("video_metadata")
    target_seconds = (
        metadata.get("target_duration_seconds")
        if isinstance(metadata, dict)
        else None
    )
    try:
        target_duration_seconds = frontend.normalize_target_duration(target_seconds)
    except ValueError as exc:
        raise P500ResumeError(
            f"existing manifest has an invalid target duration: {target_seconds!r}"
        ) from exc

    profile = frontend._duration_aware_profile(
        frontend._story_profile(topic, source or topic, variant_seed=run_dir.name),
        target_duration_seconds=target_duration_seconds,
    )
    _research_text, research = load_structured_document(run_dir / "research.md")
    if research:
        profile = frontend._profile_from_reviewed_research(profile, research)
    _story_text, story = load_structured_document(run_dir / "story.md")
    if story:
        profile = frontend._profile_from_reviewed_story(profile, story)
    return profile, manifest


def _resume_state_updates(
    *,
    run_dir: Path,
    topic: str,
    profile: dict[str, Any],
    stop_target: str,
    now: str,
) -> dict[str, str]:
    state_updates = _write_resume_orchestration(
        run_dir=run_dir,
        stop_target=stop_target,
        now=now,
    )
    state_updates.update(
        {
            "slot.p520.status": "done",
            "slot.p520.note": "asset inventory rematerialized from preserved p450 manifest",
            "slot.p530.status": "done",
            "slot.p530.note": "asset plan rematerialized; semantic review pending",
            "slot.p540.status": "pending",
            "slot.p540.note": "asset semantic review has not completed",
            "slot.p550.status": "pending",
            "slot.p550.note": "candidate requests exist but are not frozen",
            "slot.p560.status": "pending",
            "slot.p560.note": "asset generation has not completed",
            "slot.p570.status": "pending",
            "slot.p570.note": "asset continuity review has not completed",
            "slot.p620.status": "done",
            "slot.p620.note": "preserved production manifest rematerialized into candidate requests",
            "slot.p630.status": "pending",
            "slot.p630.note": "scene implementation hard review has not completed",
            "slot.p640.status": "pending",
            "slot.p640.note": "scene implementation judgment has not completed",
            "slot.p650.status": "pending",
            "slot.p650.note": "candidate requests materialized; waiting for semantic review and final freeze",
            "review.image_prompt.request_freeze.status": "draft",
            "review.image_prompt.request_freeze.request": "image_generation_requests.md",
            "review.image_prompt.request_freeze.snapshot": "image_generation_request_snapshot.json",
        }
    )
    if stop_target == "p680":
        state_updates.update(
            {
                "slot.p660.status": "pending",
                "slot.p660.note": "waiting for image-prompt semantic review and final request freeze",
                "slot.p670.status": "pending",
                "slot.p670.note": "waiting for scene image generation to finish",
                "slot.p680.status": "pending",
                "slot.p680.note": "frontend image review waits for every scene image",
            }
        )
    duration_plan = dict(profile["duration_plan"])
    state_updates.update(
        {
            "timestamp": now,
            "topic": topic,
            "status": "P650",
            "runtime.stage": "image_prompt_semantic_review_pending",
            "runtime.stage_target": "p600",
            "runtime.stop_slot": stop_target,
            "runtime.resume.p500.status": "materialized",
            "runtime.resume.p500.stop_target": stop_target,
            "runtime.target_video_seconds": str(duration_plan["target_seconds"]),
            "runtime.duration_gate.minimum_seconds": str(
                int(duration_plan["minimum_effective_seconds"])
            ),
            "runtime.duration_plan.minimum_scene_count": str(
                duration_plan["minimum_scene_count"]
            ),
            "runtime.duration_plan.minimum_narration_seconds": str(
                duration_plan["minimum_narration_seconds"]
            ),
            "runtime.scaffold.content_status": "authored",
            "runtime.review_policy": "frontend",
            "review.policy.story": "required",
            "review.policy.image": "required",
            "review.policy.narration": "optional",
            "gate.research_review": "required",
            "gate.story_review": "required",
            "gate.narration_review": "optional",
            "immersive.experience": "cinematic_story",
            "review.research.status": "approved",
            "review.story.status": "approved",
            "review.script.status": "approved",
            "stage.research.status": "reviewed",
            "stage.story.status": "reviewed",
            "stage.asset.status": "in_progress",
            "stage.scene_implementation.status": "in_progress",
            "review.image.status": "pending",
            "gate.image_review": "required",
        }
    )
    return state_updates


def _write_resume_orchestration(
    *,
    run_dir: Path,
    stop_target: str,
    now: str,
) -> dict[str, str]:
    orchestration_dir = run_dir / "logs" / "orchestration"
    orchestration_dir.mkdir(parents=True, exist_ok=True)
    progress_path = orchestration_dir / "l2_supervisor_progress.md"
    if not progress_path.exists():
        progress_path.write_text(
            "| timestamp | bucket | supervisor | event | stop_slot | result | note |\n"
            "|---|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    progress_rows: list[str] = []
    state_updates: dict[str, str] = {}
    bucket_specs = (
        (
            "p500",
            ("p510", "p520", "p530", "p540", "p550", "p560", "p570"),
            (
                "asset_inventory.md",
                "asset_plan.md",
                "asset_generation_requests.md",
                "asset_generation_manifest.md",
            ),
            "pending",
            "p600",
        ),
        (
            "p600",
            (
                ("p610", "p620", "p630", "p640", "p650", "p660", "p670", "p680")
                if stop_target == "p680"
                else ("p610", "p620", "p630", "p640", "p650")
            ),
            ("image_generation_requests.md",),
            "pending",
            None,
        ),
    )
    for bucket, slots, artifacts, status, next_bucket in bucket_specs:
        result_rel = f"logs/orchestration/{bucket}.supervisor_result.json"
        progress_rows.extend(
            [
                f"| {now} | {bucket} | {bucket} P-Bucket Supervisor | invoked | {stop_target} | - | p500 resume |",
                f"| {now} | {bucket} | {bucket} P-Bucket Supervisor | returned | {stop_target} | {result_rel} | {status} |",
            ]
        )
        key = f"orchestration.{bucket}.supervisor"
        state_updates.update(
            {
                f"{key}.call_status": "returned",
                f"{key}.status": status,
                f"{key}.finished_at": now,
            }
        )
        result = {
            "bucket": bucket,
            "status": "pending",
            "stop_slot": stop_target,
            "completed_slots": (
                ["p520", "p530"]
                if bucket == "p500"
                else ["p620"]
            ),
            "required_artifacts": [
                {"path": path, "exists": (run_dir / path).is_file()}
                for path in artifacts
            ],
            "state_keys": {
                f"slot.{slots[-1]}.status": (
                    "pending"
                )
            },
            "review_outputs": [],
            "next_bucket": next_bucket,
        }
        (orchestration_dir / f"{bucket}.supervisor_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    with progress_path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(progress_rows) + "\n")
    return state_updates


def materialize_from_p500(
    frontend: ModuleType,
    *,
    run_dir: Path,
    topic: str,
    source: str,
    stop_target: str,
) -> None:
    profile, manifest = _resume_profile(
        frontend,
        run_dir=run_dir,
        topic=topic,
        source=source,
    )
    for rel in (
        "assets/characters",
        "assets/objects",
        "assets/locations",
        "assets/scenes",
        "assets/audio",
        "logs/grounding",
    ):
        (run_dir / rel).mkdir(parents=True, exist_ok=True)

    now = frontend._now_iso()
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "runtime.stage": "p500_resume_materializing",
            "runtime.resume.p500.status": "materializing",
            "last_error": "",
        },
    )
    _archive_p400_review_evidence(run_dir)
    asset_inventory, asset_plan = frontend._build_asset_artifacts_from_manifest(
        profile=profile,
        manifest=manifest,
    )
    (run_dir / "asset_inventory.md").write_text(
        frontend._md_yaml("Asset Inventory", asset_inventory),
        encoding="utf-8",
    )
    (run_dir / "asset_plan.md").write_text(
        frontend._md_yaml("Asset Plan", asset_plan),
        encoding="utf-8",
    )
    frontend._write_review_artifacts(run_dir)
    _prepare_stage_context(run_dir, "manifest")
    frontend._require_fresh_p400_readiness(run_dir)
    frontend._write_asset_request_files(run_dir, asset_plan, profile)
    frontend._materialize_standard_request_files(run_dir)
    append_state_snapshot(
        run_dir / "state.txt",
        _resume_state_updates(
            run_dir=run_dir,
            topic=topic,
            profile=profile,
            stop_target=stop_target,
            now=now,
        ),
    )


def _archive_p400_review_evidence(run_dir: Path) -> Path:
    state = parse_state_file(run_dir / "state.txt")
    checkpoint_rel = str(state.get("runtime.resume.p500.checkpoint") or "").strip()
    if not checkpoint_rel:
        raise P500ResumeError("p500 resume checkpoint is missing from state")
    checkpoint = (run_dir / checkpoint_rel).resolve()
    try:
        checkpoint.relative_to(run_dir.resolve())
    except ValueError as exc:
        raise P500ResumeError(
            f"p500 resume checkpoint escapes the run directory: {checkpoint}"
        ) from exc
    if not (checkpoint / "checkpoint.json").is_file():
        raise P500ResumeError(f"p500 resume checkpoint is incomplete: {checkpoint}")

    root_files = {
        "visual_value_review.md",
        "scene_set_review.md",
        "scene_detail_review.md",
        "scene_intent_review.md",
        "cut_blueprint_review.md",
        "script_review.md",
        "production_readiness_review.md",
    }
    eval_stages = (
        "visual_value",
        "scene_set",
        "scene_detail",
        "cut_blueprint",
        "script",
        "production_readiness",
    )
    semantic_stages = ("scene_set", "scene_detail", "cut_blueprint")
    selected: list[str] = []
    for path in run_dir.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(run_dir).as_posix()
        if rel in root_files:
            selected.append(rel)
            continue
        if any(rel.startswith(f"logs/eval/{stage}/") for stage in eval_stages):
            selected.append(rel)
            continue
        if any(
            rel.startswith(f"logs/review/semantic/{stage}.")
            for stage in semantic_stages
        ):
            selected.append(rel)
            continue
        if rel.startswith(("logs/grounding/script.", "logs/grounding/manifest.")):
            selected.append(rel)

    evidence_root = checkpoint / "p400_evidence"
    for rel in sorted(set(selected)):
        source = run_dir / rel
        destination = evidence_root / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    (checkpoint / "p400_evidence_manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "toc.p500_resume.p400_evidence.v1",
                "files": sorted(set(selected)),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return evidence_root


def _prepare_stage_context(run_dir: Path, stage: str) -> None:
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "prepare-stage-context.py"),
            "--stage",
            stage,
            "--run-dir",
            str(run_dir),
            "--flow",
            "immersive",
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def _prepare_resume_grounding(run_dir: Path) -> None:
    for stage in ("asset", "scene_implementation"):
        _prepare_stage_context(run_dir, stage)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            "slot.p510.status": "done",
            "slot.p510.note": "asset grounding refreshed for p500 resume",
            "slot.p610.status": "done",
            "slot.p610.note": "scene implementation grounding refreshed for p500 resume",
        },
    )


def _mark_materialized_asset_requests(run_dir: Path) -> None:
    """Keep non-executed media pending while recording the p550 handoff."""

    append_state_snapshot(
        run_dir / "state.txt",
        {
            "slot.p550.status": "done",
            "slot.p550.note": "asset requests rematerialized after semantic review; media generation not requested",
            "slot.p560.status": "pending",
            "slot.p560.note": "materialize-only mode did not generate reusable assets",
            "slot.p570.status": "pending",
            "slot.p570.note": "asset continuity review waits for reusable asset generation",
            "stage.asset.status": "in_progress",
        },
    )


def _finalize_resume_orchestration(
    *,
    run_dir: Path,
    stop_target: str,
) -> dict[str, str]:
    state = parse_state_file(run_dir / "state.txt")
    bucket_slots = {
        "p500": ("p510", "p520", "p530", "p540", "p550", "p560", "p570"),
        "p600": (
            ("p610", "p620", "p630", "p640", "p650", "p660", "p670", "p680")
            if stop_target == "p680"
            else ("p610", "p620", "p630", "p640", "p650")
        ),
    }
    orchestration_dir = run_dir / "logs" / "orchestration"
    for bucket, slots in bucket_slots.items():
        path = orchestration_dir / f"{bucket}.supervisor_result.json"
        try:
            result = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise P500ResumeError(
                f"resume supervisor result is missing or invalid: {path}"
            ) from exc
        result["status"] = "done"
        result["completed_slots"] = [
            slot
            for slot in slots
            if state.get(f"slot.{slot}.status")
            in {"done", "skipped", "awaiting_approval"}
        ]
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    progress_path = orchestration_dir / "l2_supervisor_progress.md"
    with progress_path.open("a", encoding="utf-8") as handle:
        for bucket in ("p500", "p600"):
            handle.write(
                f"| {state.get('timestamp', '')} | {bucket} | "
                f"{bucket} P-Bucket Supervisor | completed | {stop_target} | "
                f"logs/orchestration/{bucket}.supervisor_result.json | validated p500 resume |\n"
            )
    return {
        "orchestration.p500.supervisor.status": "done",
        "orchestration.p600.supervisor.status": "done",
    }


def _continue_run(
    *,
    run_dir: Path,
    topic: str,
    source: str,
    stop_target: str,
    materialize_only: bool,
    skip_validation: bool,
) -> None:
    frontend = _load_frontend_runner()
    materialize_stop_target = (
        "p650" if materialize_only and stop_target == "p680" else stop_target
    )
    with frontend._run_materialization_lock(run_dir):
        materialize_from_p500(
            frontend,
            run_dir=run_dir,
            topic=topic,
            source=source,
            stop_target=materialize_stop_target,
        )
        _prepare_resume_grounding(run_dir)
        if materialize_only:
            asyncio.run(
                frontend.run_pre_media_semantic_pipeline(
                    run_dir,
                    image_prompt_provider_ready=False,
                )
            )
            _mark_materialized_asset_requests(run_dir)
        else:
            asyncio.run(frontend.generate_images(run_dir, stop_target))
            if stop_target == "p650":
                from server import image_gen_app

                image_gen_app._mark_asset_generation_handoff(
                    run_dir,
                    asset_quality_passed=False,
                )
        frontend.write_run_index(run_dir)
        if not skip_validation:
            if materialize_only:
                from server import image_gen_app

                image_gen_app._validate_materialized_p650_run(
                    frontend._run_id_from_dir(run_dir)
                )
            else:
                frontend.validate(run_dir, stop_target)
        final_updates = (
            {}
            if materialize_only
            else _finalize_resume_orchestration(
                run_dir=run_dir,
                stop_target=stop_target,
            )
        )
        append_state_snapshot(
            run_dir / "state.txt",
            {
                **final_updates,
                "runtime.resume.p500.status": (
                    "semantic_materialized" if materialize_only else "completed"
                ),
                "runtime.resume.p500.stop_target": stop_target,
            },
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Safely reset an existing frontend-created ToC run and resume it from p500."
    )
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--topic", default="")
    parser.add_argument("--source", default="")
    parser.add_argument("--checkpoint-id", default="")
    parser.add_argument(
        "--plan-token",
        default="",
        help="Exact plan_token returned by the inspected dry-run.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the reset. Without this flag, print a dry-run plan only.",
    )
    parser.add_argument(
        "--continue-to",
        choices=["p650", "p680"],
        help="After reset, continue the same run through this stop target.",
    )
    parser.add_argument(
        "--materialize-only",
        action="store_true",
        help="Run semantic materialization but do not generate media.",
    )
    parser.add_argument("--skip-validation", action="store_true")
    args = parser.parse_args()

    if args.continue_to and not args.apply:
        parser.error("--continue-to requires --apply")
    if args.materialize_only and not args.continue_to:
        parser.error("--materialize-only requires --continue-to")
    if args.apply and (not args.checkpoint_id.strip() or not args.plan_token.strip()):
        parser.error(
            "--apply requires the --checkpoint-id and --plan-token returned by dry-run"
        )

    try:
        resolved = resolve_run_dir(REPO_ROOT, args.run_dir)
        topic = _topic_for_run(resolved, args.topic)
        checkpoint_id = args.checkpoint_id.strip() or None
        if not args.apply:
            plan, _checkpoint = prepare_p500_resume(
                repo_root=REPO_ROOT,
                run_dir=resolved,
                apply=False,
                checkpoint_id=checkpoint_id,
            )
            print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
            return

        if args.continue_to:
            try:
                with sync_file_lock(
                    resolved / ".locks" / "create_resume.lock",
                    wait=False,
                ):
                    plan = build_resume_plan(
                        repo_root=REPO_ROOT,
                        run_dir=resolved,
                        checkpoint_id=checkpoint_id,
                    )
                    if args.plan_token.strip() != plan.plan_token:
                        raise P500ResumeError(
                            "dry-run plan token is stale; inspect a new dry-run before apply"
                        )
                    checkpoint = apply_resume_plan(plan, lock_already_held=True)
                    _continue_run(
                        run_dir=resolved,
                        topic=topic,
                        source=args.source.strip() or topic,
                        stop_target=args.continue_to,
                        materialize_only=args.materialize_only,
                        skip_validation=args.skip_validation,
                    )
            except FileLockUnavailable as exc:
                raise P500ResumeError(
                    f"another create/resume process owns this run: {resolved}"
                ) from exc
        else:
            plan = build_resume_plan(
                repo_root=REPO_ROOT,
                run_dir=resolved,
                checkpoint_id=checkpoint_id,
            )
            if args.plan_token.strip() != plan.plan_token:
                raise P500ResumeError(
                    "dry-run plan token is stale; inspect a new dry-run before apply"
                )
            checkpoint = apply_resume_plan(plan)
        print(f"Run dir: {resolved}")
        print(f"Checkpoint: {checkpoint}")
        print(f"Moved downstream files: {len(plan.downstream_files)}")
        print(f"Stop target: {args.continue_to or 'p500 prepared'}")
    except subprocess.CalledProcessError as exc:
        detail = str(exc.stderr or exc.stdout or exc).strip()
        parser.exit(1, f"p500 resume failed: {detail}\n")
    except (P500ResumeError, RuntimeError) as exc:
        parser.exit(1, f"p500 resume failed: {exc}\n")


if __name__ == "__main__":
    main()
