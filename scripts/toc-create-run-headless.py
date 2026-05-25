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


def _check_cut_contract_v2(run_dir: Path, *, generate_images: bool) -> list[str]:
    failures: list[str] = []
    manifest_path = run_dir / "video_manifest.md"
    script_path = run_dir / "script.md"
    image_requests_path = run_dir / "image_generation_requests.md"
    if not manifest_path.exists():
        return ["missing video_manifest.md"]
    _text, manifest = load_structured_document(manifest_path)
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
    if script_path.exists():
        _script_text, script = load_structured_document(script_path)
        scenes = script.get("scenes", []) if isinstance(script.get("scenes"), list) else []
        if len(scenes) < 7:
            failures.append(f"script has too few scenes for maximal meaningful policy ({len(scenes)}/7)")
    if image_requests_path.exists():
        request_text = image_requests_path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\bmotion_brief\b|motion_contract", request_text):
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


def _write_report(*, run_dir: Path, job: dict[str, Any], generate_images: bool, assertion_failures: list[str]) -> Path:
    report_dir = run_dir / "logs" / "regression"
    report_dir.mkdir(parents=True, exist_ok=True)
    state = _parse_state(run_dir / "state.txt")
    lines = [
        "# Headless Create Regression Report",
        "",
        f"- job_id: `{job.get('jobId', '')}`",
        f"- run_id: `{job.get('runId', '')}`",
        f"- status: `{job.get('status', '')}`",
        f"- generate_images: `{str(generate_images).lower()}`",
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
    report = report_dir / "headless_regression_report.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


async def create_run_via_frontend_route(
    *,
    title: str,
    source: str,
    generate_images: bool,
    timeout_seconds: float,
    poll_interval: float,
    base_url: str | None = None,
) -> dict[str, Any]:
    os.environ.setdefault("TOC_SERVER_AUTH_DISABLED", "1")
    if base_url:
        client_cm = httpx.AsyncClient(base_url=base_url.rstrip("/"))
    else:
        from server.app import app  # noqa: WPS433

        client_cm = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://toc-headless.local",
        )
    async with client_cm as client:
        created = await client.post(
            "/api/image-gen/runs/create",
            json={"title": title, "source": source, "generate_images": generate_images},
        )
        created.raise_for_status()
        job = created.json()
        job_id = str(job["jobId"])
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            latest = await client.get(f"/api/image-gen/runs/create/{job_id}")
            latest.raise_for_status()
            job = latest.json()
            if job.get("status") in {"completed", "failed"}:
                return job
            await asyncio.sleep(poll_interval)
        raise TimeoutError(f"create job did not finish within {timeout_seconds:.0f}s: {job_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless ToC create regression through the frontend backend route.")
    parser.add_argument("--title", required=True)
    parser.add_argument("--source", default="")
    parser.add_argument("--no-images", action="store_true", help="Disable image generation. Images are generated by default.")
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
            timeout_seconds=args.timeout_seconds,
            poll_interval=args.poll_interval,
            base_url=args.base_url.strip() or None,
        )
    )
    run_dir = REPO_ROOT / str(job.get("path") or "")
    assertion_failures: list[str] = []
    if job.get("status") != "completed":
        assertion_failures.append(f"create job failed: {job.get('error') or job.get('errorCode') or 'unknown error'}")
    if args.assert_profile == "cut_contract_v2" and run_dir.exists():
        assertion_failures.extend(_check_cut_contract_v2(run_dir, generate_images=generate_images))
    report = _write_report(run_dir=run_dir, job=job, generate_images=generate_images, assertion_failures=assertion_failures)
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
