#!/usr/bin/env python3

from __future__ import annotations

import argparse
import asyncio
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error

from kindle_web_cdp import CdpPage, export_blob_image, read_state, turn_page, wait_for_reader


ROOT = pathlib.Path(__file__).resolve().parent
OCR_SWIFT = ROOT / "ocr-apple-vision.swift"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract visible Kindle for Web pages by connecting directly to a Chrome "
            "remote-debugging session and exporting the page image from the reader DOM."
        )
    )
    parser.add_argument("--run-dir", required=True, help="Target run directory under kindle/runs/<timestamp>.")
    parser.add_argument("--pages", type=int, default=5, help="How many visible pages to export. Default: 5.")
    parser.add_argument("--port", type=int, default=59708, help="Chrome remote-debugging port. Default: 59708.")
    parser.add_argument(
        "--ocr-mode",
        choices=["none", "auto", "apple-vision", "tesseract"],
        default="none",
        help=(
            "How to populate transcript.txt during export. "
            "'none' leaves placeholders for a later Codex vision pass."
        ),
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=600,
        help="How long to wait for a Kindle reader tab before failing. Default: 600.",
    )
    parser.add_argument(
        "--poll-sec",
        type=float,
        default=2.0,
        help="Polling interval while waiting for the reader. Default: 2.0.",
    )
    return parser.parse_args()


def log(message: str) -> None:
    print(message, file=sys.stderr)


def ensure_run_files(run_dir: pathlib.Path, page_count: int) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    pages_dir = run_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    transcript_path = run_dir / "transcript.txt"
    session_path = run_dir / "session.md"
    if not transcript_path.exists():
        lines = [f"=== Page {index + 1} ===\n[[pending]]" for index in range(page_count)]
        transcript_path.write_text("\n\n".join(lines) + "\n", encoding="utf-8")
    return pages_dir, transcript_path, session_path


def write_transcript(path: pathlib.Path, entries: list[str]) -> None:
    blocks = []
    for index, text in enumerate(entries, start=1):
        body = text if text else "[[pending]]"
        blocks.append(f"=== Page {index} ===\n{body}")
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def clean_ocr_text(text: str) -> str:
    lines = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if not line:
            continue
        lines.append(line)
    return "\n".join(lines)


def run_subprocess(command: list[str], *, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=True,
    )


def ocr_with_vision(image_path: pathlib.Path) -> str | None:
    if not OCR_SWIFT.exists():
        return None
    try:
        result = run_subprocess(["swift", str(OCR_SWIFT), str(image_path)], timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
    text = clean_ocr_text(result.stdout)
    return text or None


def ocr_with_tesseract(image_path: pathlib.Path) -> str | None:
    executable = shutil.which("tesseract")
    if executable is None:
        return None
    try:
        result = run_subprocess(
            [executable, str(image_path), "stdout", "-l", "jpn+eng", "--psm", "6"],
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    text = clean_ocr_text(result.stdout)
    return text or None


def ocr_image(image_path: pathlib.Path) -> tuple[str, str]:
    vision_text = ocr_with_vision(image_path)
    if vision_text:
        return vision_text, "apple-vision"
    tesseract_text = ocr_with_tesseract(image_path)
    if tesseract_text:
        return tesseract_text, "tesseract"
    return "[[transcription failed]]", "failed"


def transcribe_image(image_path: pathlib.Path, mode: str) -> tuple[str, str]:
    if mode == "none":
        return "[[pending vision transcription]]", "pending"
    if mode == "apple-vision":
        text = ocr_with_vision(image_path)
        return (text, "apple-vision") if text else ("[[transcription failed]]", "failed")
    if mode == "tesseract":
        text = ocr_with_tesseract(image_path)
        return (text, "tesseract") if text else ("[[transcription failed]]", "failed")
    return ocr_image(image_path)


def write_session(
    path: pathlib.Path,
    *,
    run_dir: pathlib.Path,
    page_target: int,
    status: str,
    transcription_source: str,
    start_page: int | None,
    end_page: int | None,
    page_turn_method: str,
    notes: list[str],
) -> None:
    lines = [
        "# Kindle session",
        "",
        f"- run_dir: `{run_dir}`",
        "- target: `https://read.amazon.com`",
        f"- page_target: `{page_target}`",
        "- login_mode: manual",
        f"- transcription_source: {transcription_source}",
        f"- page_turn_method: `{page_turn_method}`",
        f"- start_book_page: `{start_page if start_page is not None else 'unknown'}`",
        f"- end_book_page: `{end_page if end_page is not None else 'unknown'}`",
        f"- status: {status}",
        "",
        "## Notes",
        "",
    ]
    if notes:
        lines.extend([f"- {note}" for note in notes])
    else:
        lines.append("- No notes recorded.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main_async(args: argparse.Namespace) -> int:
    run_dir = pathlib.Path(args.run_dir).resolve()
    pages_dir, transcript_path, session_path = ensure_run_files(run_dir, args.pages)
    notes: list[str] = []
    transcriptions = ["[[pending]]"] * args.pages
    page_turn_method = "unknown"
    start_page = None
    end_page = None

    try:
        target, initial_state = await wait_for_reader(args.port, args.timeout_sec, args.poll_sec)
    except Exception as exc:
        write_session(
            session_path,
            run_dir=run_dir,
            page_target=args.pages,
            status="failed",
            transcription_source="cdp-direct-page-image-export; reader not reached",
            start_page=None,
            end_page=None,
            page_turn_method="not-reached",
            notes=[str(exc)],
        )
        raise

    notes.append(f"Connected to Kindle reader tab: {target.get('url', 'unknown')}")
    start_page = initial_state.get("currentPage")
    notes.append(f"Started from visible Kindle page {start_page}.")

    async with CdpPage(target["webSocketDebuggerUrl"]) as page:
        for index in range(args.pages):
            state = await read_state(page)
            current_page = state.get("currentPage")
            if current_page is not None:
                notes.append(f"Exporting transcript page {index + 1} from Kindle page {current_page}.")
            image_path = pages_dir / f"{index + 1:04d}.png"
            await export_blob_image(page, image_path)
            text, source = transcribe_image(image_path, args.ocr_mode)
            if source == "pending":
                transcriptions[index] = text
                notes.append(f"Page {index + 1} image exported; awaiting Codex vision transcription.")
            elif source == "failed":
                transcriptions[index] = "[[transcription failed]]"
                notes.append(f"Page {index + 1} OCR failed.")
            elif source == "tesseract":
                transcriptions[index] = f"[[partial OCR]]\n{text}"
                notes.append(f"Page {index + 1} used tesseract OCR fallback.")
            else:
                transcriptions[index] = text
            write_transcript(transcript_path, transcriptions)
            end_page = current_page
            if index == args.pages - 1:
                continue
            method = await turn_page(page, current_page if isinstance(current_page, int) else None)
            if page_turn_method == "unknown":
                page_turn_method = method
            await asyncio.sleep(1.5)
            new_state = await read_state(page)
            if isinstance(new_state.get("currentPage"), int):
                end_page = new_state["currentPage"]

    status = "completed"
    if args.ocr_mode == "none":
        status = "exported"
    elif any(block.startswith("[[transcription failed]]") or block.startswith("[[partial OCR]]") for block in transcriptions):
        status = "partial"
    transcription_source = "cdp-direct-page-image-export + apple-vision/tesseract OCR"
    if args.ocr_mode == "none":
        transcription_source = "cdp-direct-page-image-export only; awaiting Codex vision transcription"
    elif args.ocr_mode == "apple-vision":
        transcription_source = "cdp-direct-page-image-export + apple-vision OCR"
    elif args.ocr_mode == "tesseract":
        transcription_source = "cdp-direct-page-image-export + tesseract OCR"
    write_session(
        session_path,
        run_dir=run_dir,
        page_target=args.pages,
        status=status,
        transcription_source=transcription_source,
        start_page=start_page,
        end_page=end_page,
        page_turn_method=page_turn_method,
        notes=notes,
    )
    return 0


def main() -> int:
    args = parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        log("Interrupted.")
        return 130
    except urllib.error.URLError as exc:
        log(f"Failed to reach Chrome DevTools endpoint on port {args.port}: {exc}")
        return 1
    except Exception as exc:
        log(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
