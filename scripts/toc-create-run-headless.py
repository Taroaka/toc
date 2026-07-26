#!/usr/bin/env python3
"""Create a ToC run through the same backend create route used by the frontend.

This is a regression helper for design changes. It calls
`POST /api/image-gen/runs/create` in-process, polls the matching job endpoint,
and writes a compact report under the created run directory.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import load_structured_document  # noqa: E402


OUTPUT_ROOT = (REPO_ROOT / "output").resolve()


def _parse_state(path: Path) -> dict[str, str]:
    state: dict[str, str] = {}
    if not path.exists():
        return state
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        state[key.strip()] = value.strip()
    return state


def _iter_manifest_cuts(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    cuts: list[dict[str, Any]] = []
    for scene in manifest.get("scenes", []) if isinstance(manifest.get("scenes"), list) else []:
        if not isinstance(scene, dict):
            continue
        for cut in scene.get("cuts", []) if isinstance(scene.get("cuts"), list) else []:
            if isinstance(cut, dict):
                cuts.append(cut)
    return cuts


def _check_cut_contract_v2(
    run_dir: Path,
    *,
    generate_images: bool,
    target_duration_seconds: int = 300,
    expected_title: str = "",
) -> list[str]:
    failures: list[str] = []
    manifest_path = run_dir / "video_manifest.md"
    image_requests_path = run_dir / "image_generation_requests.md"
    script_path = run_dir / "script.md"
    state_path = run_dir / "state.txt"
    for required_path in (state_path, script_path, manifest_path, image_requests_path):
        if not required_path.is_file() or required_path.is_symlink():
            failures.append(f"missing or unsafe {required_path.name}")
    if not manifest_path.exists():
        return failures
    _text, manifest = load_structured_document(manifest_path)
    metadata = manifest.get("video_metadata") if isinstance(manifest.get("video_metadata"), dict) else {}
    try:
        manifest_target = int(metadata.get("target_duration_seconds"))
    except (TypeError, ValueError):
        manifest_target = 0
    if manifest_target != target_duration_seconds:
        failures.append(
            "video_manifest target duration mismatch: "
            f"expected={target_duration_seconds}, got={manifest_target or '(missing)'}"
        )
    manifest_topic = str(metadata.get("topic") or "").strip()
    if expected_title and manifest_topic and manifest_topic != expected_title:
        failures.append(
            f"video_manifest topic mismatch: expected={expected_title!r}, got={manifest_topic!r}"
        )
    state = _parse_state(state_path)
    state_topic = state.get("topic", "").strip()
    if expected_title and state_topic != expected_title:
        failures.append(f"state topic mismatch: expected={expected_title!r}, got={state_topic or '(missing)'!r}")
    try:
        state_target = int(state.get("runtime.target_video_seconds", ""))
    except ValueError:
        state_target = 0
    if state_target != target_duration_seconds:
        failures.append(
            "state target duration mismatch: "
            f"expected={target_duration_seconds}, got={state_target or '(missing)'}"
        )
    cuts = _iter_manifest_cuts(manifest)
    if not cuts:
        failures.append("manifest has no cuts")
    for index, cut in enumerate(cuts, start=1):
        selector = str(cut.get("selector") or f"cut[{index}]")
        contract = cut.get("cut_contract")
        if not isinstance(contract, dict):
            failures.append(f"{selector}: missing cut_contract")
            continue
        viewer = contract.get("viewer_contract") if isinstance(contract.get("viewer_contract"), dict) else {}
        first_frame = contract.get("first_frame_contract") if isinstance(contract.get("first_frame_contract"), dict) else {}
        motion = contract.get("motion_contract") if isinstance(contract.get("motion_contract"), dict) else {}
        narration = contract.get("narration_contract") if isinstance(contract.get("narration_contract"), dict) else {}
        handoff = contract.get("downstream_handoff") if isinstance(contract.get("downstream_handoff"), dict) else {}
        required = {
            "cut_function": contract.get("cut_function"),
            "viewer_contract.target_beat": viewer.get("target_beat"),
            "viewer_contract.visual_proof": viewer.get("visual_proof"),
            "first_frame_contract.first_frame_brief": first_frame.get("first_frame_brief"),
            "motion_contract.motion_brief": motion.get("motion_brief"),
            "narration_contract.role": narration.get("role"),
            "downstream_handoff": handoff,
        }
        for key, value in required.items():
            if value in (None, "", [], {}):
                failures.append(f"{selector}: missing {key}")
    planned_duration = 0.0
    for cut in cuts:
        video_generation = cut.get("video_generation") if isinstance(cut.get("video_generation"), dict) else {}
        try:
            planned_duration += float(video_generation.get("duration_seconds") or 0)
        except (TypeError, ValueError):
            pass
    minimum_effective_duration = target_duration_seconds * 0.8
    if planned_duration < minimum_effective_duration:
        failures.append(
            "planned cut duration is below 80% of requested target: "
            f"{planned_duration:g}/{target_duration_seconds}s"
        )
    if image_requests_path.is_file() and not image_requests_path.is_symlink():
        request_text = image_requests_path.read_text(encoding="utf-8", errors="replace")
        api_prompt_blocks = re.findall(
            r"```api_prompt[^\n]*\n(.*?)\n```",
            request_text,
            flags=re.DOTALL,
        )
        if any(re.search(r"\bmotion_brief\b|\bmotion_contract\b", block) for block in api_prompt_blocks):
            failures.append("image_generation_requests.md leaks motion_brief/motion_contract into image prompts")
    if not generate_images:
        generated = [
            path
            for rel in ("assets/scenes", "assets/characters", "assets/objects", "assets/locations")
            for path in (run_dir / rel).glob("*.png")
            if path.is_file()
        ]
        if generated:
            failures.append(f"--no-images created image files unexpectedly ({len(generated)})")
    return failures


def _safe_report_path(run_dir: Path) -> Path:
    resolved_run_dir = run_dir.resolve(strict=True)
    relative = Path("logs/regression/headless_regression_report.md")
    current = resolved_run_dir
    for part in relative.parent.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"headless report path contains a symlink: {current}")
        current.mkdir(exist_ok=True)
        try:
            current.resolve(strict=True).relative_to(resolved_run_dir)
        except ValueError as exc:
            raise ValueError(f"headless report directory escaped run: {current}") from exc
    report = resolved_run_dir / relative
    if report.is_symlink():
        raise ValueError(f"headless report file must not be a symlink: {report}")
    return report


def _write_report(
    *,
    run_dir: Path,
    job: dict[str, Any],
    generate_images: bool,
    assertion_failures: list[str],
    target_duration_seconds: int | None = None,
) -> Path:
    report = _safe_report_path(run_dir)
    state = _parse_state(run_dir / "state.txt")
    lines = [
        "# Headless Create Regression Report",
        "",
        f"- job_id: `{job.get('jobId', '')}`",
        f"- run_id: `{job.get('runId', '')}`",
        f"- status: `{job.get('status', '')}`",
        f"- generate_images: `{str(generate_images).lower()}`",
        f"- target_duration_seconds: `{target_duration_seconds if target_duration_seconds is not None else job.get('targetDurationSeconds', 300)}`",
        f"- path: `{job.get('path', '')}`",
        f"- runtime.stage: `{state.get('runtime.stage', '')}`",
        f"- runtime.stop_slot: `{state.get('runtime.stop_slot', '')}`",
        "",
        "## Assertions",
        "",
    ]
    if assertion_failures:
        lines.extend(f"- failed: {failure}" for failure in assertion_failures)
    else:
        lines.append("- passed")
    lines.append("")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(report, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))
    return report


async def create_run_via_frontend_route(
    *,
    title: str,
    source: str,
    generate_images: bool,
    timeout_seconds: float,
    poll_interval: float,
    target_duration_seconds: int = 300,
    base_url: str | None = None,
) -> dict[str, Any]:
    existing_run_ids = {
        path.name
        for path in OUTPUT_ROOT.iterdir()
        if path.is_dir()
    } if OUTPUT_ROOT.exists() else set()
    if base_url:
        client_cm = httpx.AsyncClient(base_url=base_url.rstrip("/"))
    else:
        # Mount only the create router in a private ASGI app.  This keeps the
        # intentionally in-process regression call isolated instead of
        # changing process-global authentication environment variables.
        from fastapi import FastAPI  # noqa: WPS433
        from server.image_gen_app import router  # noqa: WPS433

        app = FastAPI(title="ToC Headless Regression")
        app.include_router(router)

        client_cm = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://toc-headless.local",
        )
    async with client_cm as client:
        created = await client.post(
            "/api/image-gen/runs/create",
            json={
                "title": title,
                "source": source,
                "generate_images": generate_images,
                "target_duration_seconds": target_duration_seconds,
            },
        )
        created.raise_for_status()
        job = created.json()
        if not isinstance(job, dict):
            raise RuntimeError("create response must be a JSON object")
        job_id = str(job.get("jobId") or "").strip()
        if not job_id:
            raise RuntimeError("create response is missing jobId")
        expected_run_id = str(job.get("runId") or "").strip()
        expected_path = str(job.get("path") or "").strip()
        if not expected_run_id or not expected_path:
            raise RuntimeError("create response must bind jobId to an initial runId and path")
        if expected_run_id in existing_run_ids:
            raise RuntimeError(f"create response replayed a pre-existing runId: {expected_run_id}")
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            latest = await client.get(f"/api/image-gen/runs/create/{job_id}")
            latest.raise_for_status()
            job = latest.json()
            if not isinstance(job, dict):
                raise RuntimeError("create status response must be a JSON object")
            latest_job_id = str(job.get("jobId") or "").strip()
            if latest_job_id != job_id:
                raise RuntimeError(
                    f"create status identity changed: expected jobId {job_id!r}, got {latest_job_id!r}"
                )
            latest_run_id = str(job.get("runId") or "").strip()
            latest_path = str(job.get("path") or "").strip()
            if expected_run_id and latest_run_id != expected_run_id:
                raise RuntimeError(
                    f"create status identity changed: expected runId {expected_run_id!r}, got {latest_run_id!r}"
                )
            if expected_path and latest_path != expected_path:
                raise RuntimeError(
                    f"create status identity changed: expected path {expected_path!r}, got {latest_path!r}"
                )
            expected_run_id = expected_run_id or latest_run_id
            expected_path = expected_path or latest_path
            if job.get("status") in {"completed", "failed"}:
                return job
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"create job did not finish within {timeout_seconds:.0f}s: {job_id}")


def _resolve_completed_run_dir(job: dict[str, Any]) -> Path:
    run_id = str(job.get("runId") or "").strip()
    raw_path = str(job.get("path") or "").strip()
    if not run_id:
        raise ValueError("completed create response is missing runId")
    if not raw_path:
        raise ValueError("completed create response is missing path")
    if Path(run_id).name != run_id or "/" in run_id or "\\" in run_id:
        raise ValueError(f"completed create runId must be one top-level directory name: {run_id!r}")
    candidate = Path(raw_path)
    resolved = (
        candidate.resolve()
        if candidate.is_absolute()
        else (REPO_ROOT / candidate).resolve()
    )
    try:
        resolved.relative_to(OUTPUT_ROOT)
    except ValueError as exc:
        raise ValueError(
            f"completed create path must stay under {OUTPUT_ROOT}: {raw_path!r}"
        ) from exc
    if resolved == OUTPUT_ROOT or resolved.parent != OUTPUT_ROOT or resolved.name != run_id:
        raise ValueError(
            f"completed create path/runId mismatch: path={raw_path!r}, runId={run_id!r}"
        )
    if not resolved.is_dir():
        raise ValueError(f"completed create run directory does not exist: {resolved}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless ToC create regression through the frontend backend route.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--no-images", action="store_true", help="Disable image generation. Images are generated by default.")
    parser.add_argument("--target-duration-seconds", type=int, default=300, help="Target video duration in seconds (300-1200).")
    parser.add_argument("--base-url", default="", help="Optional running backend URL, e.g. http://127.0.0.1:8000. Omit for in-process ASGI.")
    parser.add_argument("--assert-profile", choices=["none", "cut_contract_v2"], default="cut_contract_v2")
    parser.add_argument("--timeout-seconds", type=float, default=7200)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    args = parser.parse_args()

    source = args.source.strip() or args.title
    generate_images = not args.no_images
    job = asyncio.run(
        create_run_via_frontend_route(
            title=args.title,
            source=source,
            generate_images=generate_images,
            target_duration_seconds=args.target_duration_seconds,
            timeout_seconds=args.timeout_seconds,
            poll_interval=args.poll_interval,
            base_url=args.base_url.strip() or None,
        )
    )
    assertion_failures: list[str] = []
    if job.get("status") != "completed":
        assertion_failures.append(f"create job failed: {job.get('error') or job.get('errorCode') or 'unknown error'}")
    try:
        run_dir = _resolve_completed_run_dir(job)
    except ValueError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    if args.assert_profile == "cut_contract_v2":
        assertion_failures.extend(
            _check_cut_contract_v2(
                run_dir,
                generate_images=generate_images,
                target_duration_seconds=args.target_duration_seconds,
                expected_title=args.title,
            )
        )
    try:
        report = _write_report(
            run_dir=run_dir,
            job=job,
            generate_images=generate_images,
            assertion_failures=assertion_failures,
            target_duration_seconds=args.target_duration_seconds,
        )
    except (OSError, ValueError) as exc:
        print(f"FAIL: cannot write contained regression report: {exc}", file=sys.stderr)
        return 1
    print(f"Run dir: {run_dir}")
    print(f"Report: {report}")
    if assertion_failures:
        for failure in assertion_failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print("Headless create regression passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
