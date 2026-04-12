#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error

from PIL import Image

from kindle_full_book_policies import EndOfBookEvidence, analyze_page_sequence, decide_retry, evaluate_end_of_book
from kindle_web_cdp import CdpPage, PageAlreadyChangedError, export_blob_image, read_state, turn_page, wait_for_reader


ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_WORKDIR = ROOT.parent


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a full-book Kindle for Web transcription using CDP page-image export "
            "and per-page Codex vision transcription."
        )
    )
    parser.add_argument(
        "--run-dir",
        help="Existing or new run directory. If omitted, a timestamped directory is created under kindle/runs/.",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from an existing run_state.json.")
    parser.add_argument("--port", type=int, default=59708, help="Chrome remote-debugging port. Default: 59708.")
    parser.add_argument("--timeout-sec", type=int, default=600, help="Wait timeout for the reader tab.")
    parser.add_argument("--poll-sec", type=float, default=2.0, help="Polling interval while waiting for the reader.")
    parser.add_argument(
        "--codex-workdir",
        default=str(DEFAULT_WORKDIR),
        help="Working directory passed to `codex exec -C`. Defaults to the repo root.",
    )
    parser.add_argument(
        "--codex-reasoning-effort",
        default="medium",
        help="Reasoning effort override passed to Codex. Default: medium.",
    )
    parser.add_argument(
        "--codex-timeout-sec",
        type=int,
        default=900,
        help="Timeout for each per-page `codex exec --image` call. Default: 900.",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        help="Optional safety cap on transcript pages for this run.",
    )
    return parser.parse_args()


def build_run_dir(run_dir_arg: str | None) -> pathlib.Path:
    if run_dir_arg:
        return pathlib.Path(run_dir_arg).expanduser().resolve()
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return (ROOT / "runs" / timestamp).resolve()


def ensure_artifacts(run_dir: pathlib.Path) -> dict[str, pathlib.Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = run_dir / "pages"
    vision_dir = run_dir / "vision"
    vision_inputs_dir = run_dir / "vision_inputs"
    pages_dir.mkdir(parents=True, exist_ok=True)
    vision_dir.mkdir(parents=True, exist_ok=True)
    vision_inputs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "run_dir": run_dir,
        "pages_dir": pages_dir,
        "vision_dir": vision_dir,
        "vision_inputs_dir": vision_inputs_dir,
        "transcript_path": run_dir / "transcript.txt",
        "session_path": run_dir / "session.md",
        "state_path": run_dir / "run_state.json",
        "manifest_path": run_dir / "manifest.json",
        "review_queue_path": run_dir / "review_queue.md",
    }


def new_state(args: argparse.Namespace, run_dir: pathlib.Path) -> dict:
    timestamp = now_iso()
    return {
        "version": 1,
        "run_dir": str(run_dir),
        "status": "pending",
        "created_at": timestamp,
        "updated_at": timestamp,
        "resume_mode": bool(args.resume),
        "login_mode": "manual",
        "transcription_source": "codex vision from local images (per-page codex exec --image)",
        "port": args.port,
        "codex_workdir": str(pathlib.Path(args.codex_workdir).expanduser().resolve()),
        "codex_reasoning_effort": args.codex_reasoning_effort,
        "reader": {
            "url": None,
            "title": None,
            "current_page": None,
            "total_pages": None,
        },
        "page_turn_method": "unknown",
        "completed_pages": 0,
        "last_completed_page_index": 0,
        "last_completed_kindle_page": None,
        "pages": [],
        "events": [],
        "review_items": [],
    }


def load_state(state_path: pathlib.Path, args: argparse.Namespace, run_dir: pathlib.Path) -> dict:
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["resume_mode"] = bool(args.resume)
        state["updated_at"] = now_iso()
        return state
    return new_state(args, run_dir)


def add_event(state: dict, message: str) -> None:
    state.setdefault("events", []).append({"ts": now_iso(), "message": message})
    state["updated_at"] = now_iso()


def print_progress(message: str) -> None:
    print(message, flush=True)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def add_review_item(
    state: dict,
    *,
    page_index: int,
    kindle_page_number: int | None,
    severity: str,
    reason: str,
    evidence: str,
    suggested_action: str,
    artifact_links: list[str] | None = None,
) -> None:
    item = {
        "page_index": page_index,
        "kindle_page_number": kindle_page_number,
        "severity": severity,
        "reason": reason,
        "evidence": evidence,
        "suggested_action": suggested_action,
        "artifact_links": artifact_links or [],
    }
    state.setdefault("review_items", []).append(item)


def page_status_from_text(text: str) -> str:
    if not text or text == "[[vision transcription failed]]":
        return "failed"
    if text.startswith("[[partial vision transcription]]"):
        return "partial"
    return "completed"


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def image_dark_ratio(path: pathlib.Path) -> float | None:
    try:
        with Image.open(path) as image:
            grayscale = image.convert("L").resize((240, 176))
            pixels = list(grayscale.getdata())
    except Exception:
        return None
    if not pixels:
        return None
    dark = sum(1 for value in pixels if value < 220)
    return dark / len(pixels)


def is_intentionally_sparse_page(dark_ratio: float | None) -> bool:
    return dark_ratio is not None and dark_ratio < 0.04


def prepare_vision_image(source_path: pathlib.Path, output_path: pathlib.Path) -> pathlib.Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source_path) as image:
        image = image.convert("RGB")
        width, height = image.size
        horizontal_pad = max(int(width * 0.08), 96)
        vertical_pad = max(int(height * 0.06), 72)
        padded = Image.new(
            "RGB",
            (width + horizontal_pad * 2, height + vertical_pad * 2),
            color=(255, 255, 255),
        )
        padded.paste(image, (horizontal_pad, vertical_pad))
        scaled = padded.resize((int(padded.width * 1.5), int(padded.height * 1.5)), Image.Resampling.LANCZOS)
        scaled.save(output_path)
    return output_path


def page_prompt() -> str:
    return """Transcribe this single Kindle page image exactly.

Rules:
- Output only the transcription text.
- This is often a Japanese vertical-writing page. Read from the far-right column toward the left, and within each column read top to bottom.
- Before answering, explicitly inspect the first visible column at the far right edge and the last visible column at the far left edge so you do not drop edge text.
- Preserve wording and factual details as faithfully as possible.
- If one or two characters are slightly unclear, make your best local guess, but do not paraphrase or normalize content.
- Keep natural paragraph breaks when they are visible on the page.
- Use `[[partial vision transcription]]` only if a meaningful part of one or more columns is actually cut off or unreadable.
- If the page is not readable enough to trust, reply exactly `[[vision transcription failed]]`.
"""


def transcribe_page_with_codex(
    *,
    image_path: pathlib.Path,
    output_path: pathlib.Path,
    log_path: pathlib.Path,
    workdir: pathlib.Path,
    reasoning_effort: str,
    timeout_sec: int,
) -> str:
    with log_path.open("w", encoding="utf-8") as log_handle:
        completed = subprocess.run(
            [
                "codex",
                "exec",
                "-C",
                str(workdir),
                "-c",
                f'model_reasoning_effort="{reasoning_effort}"',
                "--image",
                str(image_path),
                "-o",
                str(output_path),
                "-",
            ],
            input=page_prompt(),
            text=True,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            timeout=timeout_sec,
            check=False,
        )
    if completed.returncode != 0:
        raise RuntimeError(f"codex vision transcription failed for {image_path.name}. See {log_path}")
    text = output_path.read_text(encoding="utf-8").strip()
    return text or "[[vision transcription failed]]"


async def export_blob_image_with_retry(
    *,
    page: CdpPage,
    output_path: pathlib.Path,
    state: dict,
    page_index: int,
) -> None:
    attempt = 1
    while True:
        try:
            await export_blob_image(page, output_path)
            return
        except Exception as exc:
            decision = decide_retry("image_export_failed", attempt=attempt)
            add_event(state, f"Image export failed for transcript page {page_index}: {exc}")
            if not decision.should_retry:
                raise RuntimeError(
                    f"Image export failed for transcript page {page_index} after {attempt} attempts: {exc}"
                ) from exc
            add_event(
                state,
                f"Retrying image export for transcript page {page_index} in {decision.delay_seconds:.1f}s "
                f"(attempt {attempt + 1}/{decision.max_attempts}).",
            )
            await asyncio.sleep(decision.delay_seconds)
            attempt += 1


def transcribe_page_with_retry(
    *,
    image_path: pathlib.Path,
    output_path: pathlib.Path,
    log_path: pathlib.Path,
    workdir: pathlib.Path,
    reasoning_effort: str,
    timeout_sec: int,
    state: dict,
    page_index: int,
) -> str:
    attempt = 1
    while True:
        try:
            return transcribe_page_with_codex(
                image_path=image_path,
                output_path=output_path,
                log_path=log_path,
                workdir=workdir,
                reasoning_effort=reasoning_effort,
                timeout_sec=timeout_sec,
            )
        except Exception as exc:
            decision = decide_retry("vision_transcription_failed", attempt=attempt)
            add_event(state, f"Vision transcription failed for transcript page {page_index}: {exc}")
            if not decision.should_retry:
                raise RuntimeError(
                    f"Vision transcription failed for transcript page {page_index} after {attempt} attempts: {exc}"
                ) from exc
            add_event(
                state,
                f"Retrying vision transcription for transcript page {page_index} in {decision.delay_seconds:.1f}s "
                f"(attempt {attempt + 1}/{decision.max_attempts}).",
            )
            time.sleep(decision.delay_seconds)
            attempt += 1


async def turn_page_with_retry(
    *,
    page: CdpPage,
    previous_page: int | None,
    state: dict,
    page_index: int,
) -> str:
    attempt = 1
    while True:
        try:
            return await turn_page(page, previous_page)
        except PageAlreadyChangedError:
            state_after = await read_state(page)
            current_page = state_after.get("currentPage")
            if (
                previous_page is not None
                and isinstance(current_page, int)
                and current_page != previous_page
            ):
                add_event(
                    state,
                    f"Detected that the reader page had already advanced before the turn click after transcript page {page_index}.",
                )
                return "page-already-changed-verified"
            raise
        except Exception as exc:
            if "disabled" in str(exc).lower():
                raise
            decision = decide_retry("page_turn_failed", attempt=attempt)
            add_event(state, f"Page turn failed after transcript page {page_index}: {exc}")
            if not decision.should_retry:
                raise RuntimeError(
                    f"Page turn failed after transcript page {page_index} after {attempt} attempts: {exc}"
                ) from exc
            add_event(
                state,
                f"Retrying page turn after transcript page {page_index} in {decision.delay_seconds:.1f}s "
                f"(attempt {attempt + 1}/{decision.max_attempts}).",
            )
            await asyncio.sleep(decision.delay_seconds)
            attempt += 1


def rewrite_transcript(transcript_path: pathlib.Path, state: dict) -> None:
    blocks = []
    for page in state.get("pages", []):
        text = pathlib.Path(page["vision_path"]).read_text(encoding="utf-8").strip()
        if not text:
            text = "[[vision transcription failed]]"
        blocks.append(f"=== Page {page['page_index']} ===\n{text}")
    transcript_path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")


def rewrite_review_queue(review_queue_path: pathlib.Path, state: dict) -> None:
    items = sorted(
        state.get("review_items", []),
        key=lambda item: (item.get("page_index", 0), item.get("severity", "")),
    )
    lines = ["# Kindle review queue", ""]
    if not items:
        lines.append("- No review items.")
        review_queue_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return
    for item in items:
        lines.extend(
            [
                f"## Page {item.get('page_index', 'unknown')}",
                "",
                f"- kindle_page_number: `{item.get('kindle_page_number', 'unknown')}`",
                f"- severity: `{item.get('severity', 'warn')}`",
                f"- reason: {item.get('reason', 'unknown')}",
                f"- evidence: {item.get('evidence', 'unknown')}",
                f"- suggested_action: {item.get('suggested_action', 'inspect the screenshot and vision output')}",
                "- artifact_links:",
            ]
        )
        artifact_links = item.get("artifact_links") or []
        if artifact_links:
            lines.extend([f"  - `{link}`" for link in artifact_links])
        else:
            lines.append("  - none")
        lines.append("")
    review_queue_path.write_text("\n".join(lines), encoding="utf-8")


def rewrite_manifest(manifest_path: pathlib.Path, state: dict, paths: dict[str, pathlib.Path]) -> None:
    pages = state.get("pages", [])
    manifest = {
        "version": state.get("version", 1),
        "run_dir": state["run_dir"],
        "status": state["status"],
        "created_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "last_completed_page_index": state.get("last_completed_page_index", 0),
        "last_completed_kindle_page": state.get("last_completed_kindle_page"),
        "reader": state.get("reader", {}),
        "completed_pages": state.get("completed_pages", 0),
        "partial_pages": sum(1 for page in pages if page.get("quality_status") == "flagged"),
        "failed_pages": sum(1 for page in pages if page.get("quality_status") == "failed"),
        "review_items": len(state.get("review_items", [])),
        "artifacts": {
            "transcript": str(paths["transcript_path"]),
            "session": str(paths["session_path"]),
            "state": str(paths["state_path"]),
            "review_queue": str(paths["review_queue_path"]),
            "pages_dir": str(paths["pages_dir"]),
            "vision_dir": str(paths["vision_dir"]),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def rewrite_session(session_path: pathlib.Path, state: dict) -> None:
    reader = state.get("reader", {})
    events = state.get("events", [])
    lines = [
        "# Kindle full-book session",
        "",
        f"- run_dir: `{state['run_dir']}`",
        "- target: `https://read.amazon.com`",
        "- login_mode: manual",
        f"- transcription_source: {state['transcription_source']}",
        f"- page_turn_method: `{state.get('page_turn_method', 'unknown')}`",
        f"- status: {state['status']}",
        f"- completed_pages: `{state.get('completed_pages', 0)}`",
        f"- review_items: `{len(state.get('review_items', []))}`",
        f"- last_completed_transcript_page: `{state.get('last_completed_page_index', 0)}`",
        f"- last_completed_book_page: `{state.get('last_completed_kindle_page', 'unknown')}`",
        f"- reader_url: `{reader.get('url') or 'unknown'}`",
        f"- reader_title: `{reader.get('title') or 'unknown'}`",
        f"- reader_total_pages: `{reader.get('total_pages') or 'unknown'}`",
        f"- resume_mode: `{state.get('resume_mode', False)}`",
        f"- created_at: `{state.get('created_at', 'unknown')}`",
        f"- updated_at: `{state.get('updated_at', 'unknown')}`",
        "",
        "## Recent events",
        "",
    ]
    if events:
        lines.extend([f"- {event['ts']}: {event['message']}" for event in events])
    else:
        lines.append("- No events recorded.")
    session_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_state_bundle(paths: dict[str, pathlib.Path], state: dict) -> None:
    state["updated_at"] = now_iso()
    paths["state_path"].write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rewrite_transcript(paths["transcript_path"], state)
    rewrite_review_queue(paths["review_queue_path"], state)
    rewrite_session(paths["session_path"], state)
    rewrite_manifest(paths["manifest_path"], state, paths)


def next_page_index(state: dict) -> int:
    return int(state.get("last_completed_page_index", 0)) + 1


def final_status_for_stop(state: dict) -> str:
    return "partial" if state.get("review_items") else "completed"


def artifact_links_for_page(page_index: int) -> list[str]:
    return [
        f"pages/{page_index:04d}.png",
        f"vision/{page_index:04d}.txt",
        f"vision/{page_index:04d}.log",
    ]


async def align_resume_position(page: CdpPage, state: dict) -> None:
    if not state.get("resume_mode") or not state.get("pages"):
        return
    reader_state = await read_state(page)
    current_page = reader_state.get("currentPage")
    last_completed = state.get("last_completed_kindle_page")
    if not isinstance(current_page, int) or not isinstance(last_completed, int):
        raise RuntimeError(
            "Resume could not verify Kindle page numbers. Open the reader on the last completed page "
            "or the next unread page, then retry."
        )
    if current_page == last_completed:
        add_event(state, "Resume found the reader on the last completed page. Advancing once before continuing.")
        method = await turn_page(page, last_completed)
        state["page_turn_method"] = method
        await asyncio.sleep(1.5)
        return
    if current_page == last_completed + 1:
        add_event(state, "Resume confirmed the reader is already on the next unread page.")
        return
    raise RuntimeError(
        "Resume page mismatch. Open the Kindle reader on the next unread page or the last completed page, "
        f"then retry. Reader page: {current_page}, last completed book page: {last_completed}."
    )


async def main_async(args: argparse.Namespace) -> int:
    run_dir = build_run_dir(args.run_dir)
    paths = ensure_artifacts(run_dir)
    state = load_state(paths["state_path"], args, run_dir)
    if args.resume and not paths["state_path"].exists():
        raise RuntimeError(f"--resume was provided but no state file exists at {paths['state_path']}")
    if not args.resume and state.get("pages"):
        raise RuntimeError(
            f"Run directory already contains completed pages. Re-run with --resume or use a new run directory: {run_dir}"
        )

    add_event(state, "Starting full-book Kindle transcription run.")
    state["status"] = "running"
    save_state_bundle(paths, state)

    try:
        target, initial_state = await wait_for_reader(args.port, args.timeout_sec, args.poll_sec)
    except Exception as exc:
        state["status"] = "failed"
        add_event(state, f"Failed to connect to the Kindle reader tab: {exc}")
        add_event(state, "Run marked failed.")
        save_state_bundle(paths, state)
        raise

    state["reader"] = {
        "url": target.get("url"),
        "title": initial_state.get("title"),
        "current_page": initial_state.get("currentPage"),
        "total_pages": initial_state.get("totalPages"),
    }
    add_event(state, f"Connected to Kindle reader tab: {target.get('url', 'unknown')}")
    save_state_bundle(paths, state)

    try:
        async with CdpPage(target["webSocketDebuggerUrl"]) as page:
            await align_resume_position(page, state)
            save_state_bundle(paths, state)
            while True:
                page_index = next_page_index(state)
                if args.max_pages and page_index > args.max_pages:
                    state["status"] = "partial"
                    add_event(state, f"Stopped at safety cap after {args.max_pages} transcript pages.")
                    add_event(state, "Run marked partial.")
                    save_state_bundle(paths, state)
                    return 1

                current_state = await read_state(page)
                current_page = current_state.get("currentPage")
                total_pages = current_state.get("totalPages")
                state["reader"] = {
                    "url": current_state.get("href"),
                    "title": current_state.get("title"),
                    "current_page": current_page,
                    "total_pages": total_pages,
                }
                image_path = paths["pages_dir"] / f"{page_index:04d}.png"
                vision_input_path = paths["vision_inputs_dir"] / f"{page_index:04d}.png"
                vision_path = paths["vision_dir"] / f"{page_index:04d}.txt"
                vision_log_path = paths["vision_dir"] / f"{page_index:04d}.log"

                add_event(state, f"Exporting transcript page {page_index} from Kindle page {current_page}.")
                print_progress(f"[page {page_index}] export starting (kindle page {current_page})")
                await export_blob_image_with_retry(
                    page=page,
                    output_path=image_path,
                    state=state,
                    page_index=page_index,
                )
                add_event(state, f"Image export completed for transcript page {page_index}.")
                print_progress(f"[page {page_index}] export ok")

                prepare_vision_image(image_path, vision_input_path)
                add_event(state, f"Prepared padded vision input for transcript page {page_index}.")

                add_event(state, f"Running Codex vision transcription for transcript page {page_index}.")
                print_progress(f"[page {page_index}] vision starting")
                text = transcribe_page_with_retry(
                    image_path=vision_input_path,
                    output_path=vision_path,
                    log_path=vision_log_path,
                    workdir=pathlib.Path(args.codex_workdir).expanduser().resolve(),
                    reasoning_effort=args.codex_reasoning_effort,
                    timeout_sec=args.codex_timeout_sec,
                    state=state,
                    page_index=page_index,
                )
                page_status = page_status_from_text(text)
                normalized_text = normalize_text(text)
                quality_flags: list[str] = []
                quality_status = "accepted"
                page_record = {
                    "page_index": page_index,
                    "kindle_page_number": current_page,
                    "kindle_total_pages": total_pages,
                    "image_path": str(image_path),
                    "image_sha256": sha256_file(image_path),
                    "image_dark_ratio": image_dark_ratio(image_path),
                    "vision_input_path": str(vision_input_path),
                    "vision_path": str(vision_path),
                    "vision_log_path": str(vision_log_path),
                    "vision_status": page_status,
                    "vision_text": text,
                    "quality_status": quality_status,
                    "quality_flags": quality_flags,
                    "started_at": now_iso(),
                    "completed_at": now_iso(),
                }
                state.setdefault("pages", []).append(page_record)
                state["completed_pages"] = len(state["pages"])
                state["last_completed_page_index"] = page_index
                state["last_completed_kindle_page"] = current_page
                add_event(state, f"Completed transcript page {page_index} with vision status `{page_status}`.")

                if page_status in {"partial", "failed"}:
                    quality_flags.append(page_status)
                    quality_status = "failed" if page_status == "failed" else "flagged"
                    add_review_item(
                        state,
                        page_index=page_index,
                        kindle_page_number=current_page if isinstance(current_page, int) else None,
                        severity="blocker" if page_status == "failed" else "warn",
                        reason=f"vision_{page_status}",
                        evidence=f"vision_status={page_status}",
                        suggested_action="Inspect the screenshot and the matching vision log before trusting this page.",
                        artifact_links=artifact_links_for_page(page_index),
                    )
                    add_event(state, f"Queued transcript page {page_index} for review because vision_status={page_status}.")

                sparse_page = is_intentionally_sparse_page(page_record.get("image_dark_ratio"))

                if page_status == "completed" and len(normalized_text) < 40 and not sparse_page:
                    quality_flags.append("very_short_transcription")
                    quality_status = "failed"
                    add_review_item(
                        state,
                        page_index=page_index,
                        kindle_page_number=current_page if isinstance(current_page, int) else None,
                        severity="blocker",
                        reason="very_short_transcription",
                        evidence=f"normalized_length={len(normalized_text)}",
                        suggested_action="Treat this page as untrusted unless it is intentionally sparse and verified by hand.",
                        artifact_links=artifact_links_for_page(page_index),
                    )
                    add_event(state, f"Queued transcript page {page_index} for review because the transcription is extremely short.")
                elif page_status == "completed" and len(normalized_text) < 120 and not sparse_page:
                    quality_flags.append("short_transcription")
                    quality_status = "flagged" if quality_status == "accepted" else quality_status
                    add_review_item(
                        state,
                        page_index=page_index,
                        kindle_page_number=current_page if isinstance(current_page, int) else None,
                        severity="warn",
                        reason="short_transcription",
                        evidence=f"normalized_length={len(normalized_text)}",
                        suggested_action="Check whether this is an intentionally sparse page or a weak transcription.",
                        artifact_links=artifact_links_for_page(page_index),
                    )
                    add_event(state, f"Queued transcript page {page_index} for review because the transcription is shorter than expected.")
                elif page_status == "completed" and sparse_page:
                    quality_flags.append("intentionally_sparse_page")
                    add_event(
                        state,
                        f"Transcript page {page_index} is short but the page image is sparse, so it is accepted without review.",
                    )

                sequence_report = analyze_page_sequence(state["pages"])
                current_page_issues = [issue for issue in sequence_report.issues if issue.current_page_index == page_index]
                for issue in current_page_issues:
                    quality_flags.append(issue.code)
                    quality_status = "flagged" if quality_status == "accepted" else quality_status
                    add_event(state, f"Duplicate or gap signal on transcript page {page_index}: {issue.message}")
                    add_review_item(
                        state,
                        page_index=page_index,
                        kindle_page_number=current_page if isinstance(current_page, int) else None,
                        severity="warn",
                        reason=issue.code,
                        evidence=issue.message,
                        suggested_action="Compare this page against the previous page screenshot and transcript.",
                        artifact_links=artifact_links_for_page(page_index),
                    )

                page_record["quality_status"] = quality_status

                save_state_bundle(paths, state)
                print_progress(
                    f"[page {page_index}] vision {page_status}, quality {quality_status}, "
                    f"checkpoint saved ({state['completed_pages']} pages, {len(state['review_items'])} review items)"
                )

                previous_page = state["pages"][-2] if len(state["pages"]) >= 2 else None
                previous_text = None
                if previous_page is not None:
                    previous_text = pathlib.Path(previous_page["vision_path"]).read_text(encoding="utf-8").strip()
                end_decision = evaluate_end_of_book(
                    EndOfBookEvidence.from_page_records(
                        page_record,
                        previous_page,
                        next_button_enabled=(
                            None
                            if current_state.get("nextButtonDisabled") is None
                            else not bool(current_state.get("nextButtonDisabled"))
                        ),
                        reader_current_page=current_page if isinstance(current_page, int) else None,
                        reader_total_pages=total_pages if isinstance(total_pages, int) else None,
                        current_vision_text=text,
                        previous_vision_text=previous_text,
                    )
                )

                if end_decision.should_stop:
                    state["status"] = final_status_for_stop(state)
                    add_event(
                        state,
                        "End-of-book confirmed with signals: " + ", ".join(end_decision.triggered_signals),
                    )
                    add_event(state, f"Run marked {state['status']}.")
                    save_state_bundle(paths, state)
                    return 0 if state["status"] == "completed" else 1

                try:
                    method = await turn_page_with_retry(
                        page=page,
                        previous_page=current_page if isinstance(current_page, int) else None,
                        state=state,
                        page_index=page_index,
                    )
                except Exception as exc:
                    post_failure_state = None
                    try:
                        post_failure_state = await read_state(page)
                    except Exception:
                        post_failure_state = None

                    failure_end_decision = end_decision
                    if post_failure_state is not None:
                        failure_end_decision = evaluate_end_of_book(
                            EndOfBookEvidence.from_page_records(
                                page_record,
                                previous_page,
                                next_button_enabled=(
                                    None
                                    if post_failure_state.get("nextButtonDisabled") is None
                                    else not bool(post_failure_state.get("nextButtonDisabled"))
                                ),
                                reader_current_page=(
                                    post_failure_state.get("currentPage")
                                    if isinstance(post_failure_state.get("currentPage"), int)
                                    else current_page if isinstance(current_page, int) else None
                                ),
                                reader_total_pages=(
                                    post_failure_state.get("totalPages")
                                    if isinstance(post_failure_state.get("totalPages"), int)
                                    else total_pages if isinstance(total_pages, int) else None
                                ),
                                current_vision_text=text,
                                previous_vision_text=previous_text,
                            )
                        )
                    if failure_end_decision.should_stop:
                        state["status"] = final_status_for_stop(state)
                        add_event(
                            state,
                            "Confirmed end-of-book after page-turn failure with signals: "
                            + ", ".join(failure_end_decision.triggered_signals),
                        )
                        add_event(state, f"Run marked {state['status']}.")
                        save_state_bundle(paths, state)
                        return 0 if state["status"] == "completed" else 1
                    state["status"] = "partial"
                    add_event(state, f"Stopped after page-turn failure at transcript page {page_index}: {exc}")
                    add_review_item(
                        state,
                        page_index=page_index,
                        kindle_page_number=current_page if isinstance(current_page, int) else None,
                        severity="blocker",
                        reason="page_turn_failed",
                        evidence=str(exc),
                        suggested_action="Reopen the reader on the next unread page and resume the run.",
                        artifact_links=artifact_links_for_page(page_index),
                    )
                    add_event(state, "Run marked partial.")
                    save_state_bundle(paths, state)
                    return 1

                state["page_turn_method"] = method
                add_event(state, f"Advanced to the next page via `{method}`.")
                save_state_bundle(paths, state)
                print_progress(f"[page {page_index}] page turn ok via {method}")
                await asyncio.sleep(1.5)
    except KeyboardInterrupt:
        state["status"] = "interrupted"
        add_event(state, "Run interrupted by the operator.")
        add_event(state, "Run marked interrupted.")
        save_state_bundle(paths, state)
        raise
    except Exception as exc:
        if state.get("status") == "running":
            state["status"] = "failed"
        add_event(state, f"Run aborted with an unexpected error: {exc}")
        add_event(state, f"Run marked {state['status']}.")
        save_state_bundle(paths, state)
        raise


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except urllib.error.URLError as exc:
        print(f"Failed to reach Chrome DevTools endpoint on port {args.port}: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
