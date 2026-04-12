#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import textwrap
from dataclasses import dataclass


ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_WORKDIR = ROOT.parent


@dataclass(frozen=True)
class PromptVariant:
    slug: str
    title: str
    prompt: str


PROMPT_VARIANTS = [
    PromptVariant(
        slug="baseline",
        title="Baseline",
        prompt=textwrap.dedent(
            """\
            Read the attached Kindle page image directly with vision.

            Rules:
            - Reply with only the transcription text for this single page.
            - No preamble, no bullets, no markdown fences.
            - If the page is vertical Japanese, transcribe in natural reading order.
            - Keep line breaks only when they help readability.
            - The page may have wide white margins or text very close to the image edge. Read edge text carefully before deciding anything is missing.
            - Use best-effort transcription for minor uncertainty. Only start the reply with `[[partial vision transcription]]` if a meaningful span of text is actually cut off or unreadable.
            - If the page is not readable enough to trust, reply exactly `[[vision transcription failed]]`.
            """
        ),
    ),
    PromptVariant(
        slug="vertical-columns",
        title="Vertical Columns",
        prompt=textwrap.dedent(
            """\
            Transcribe this single Kindle page image exactly.

            Rules:
            - Output only the transcription text.
            - This is a Japanese vertical-writing page. Read from the far-right column toward the left, and within each column read top to bottom.
            - Before answering, explicitly inspect the first visible column at the far right edge and the last visible column at the far left edge so you do not drop edge text.
            - Preserve wording and punctuation as faithfully as possible.
            - If one or two characters are slightly unclear, make your best guess and continue.
            - Use `[[partial vision transcription]]` only if a meaningful part of one or more columns is actually cut off or unreadable.
            - If the page is not readable enough to trust, reply exactly `[[vision transcription failed]]`.
            """
        ),
    ),
    PromptVariant(
        slug="two-pass",
        title="Two Pass Self Check",
        prompt=textwrap.dedent(
            """\
            Transcribe this Kindle page image in Japanese.

            Process internally:
            1. Read the page once from the far-right vertical column to the far-left column.
            2. Read it a second time to check for dropped text near the image edges, especially the first 5-10 characters and the final 5-10 characters of the page.

            Rules:
            - Output only the final transcription text for the page.
            - No commentary, no explanations.
            - Keep natural paragraph breaks.
            - Prefer a best-effort literal transcription over declaring the page partial.
            - Use `[[partial vision transcription]]` only if more than a short phrase is unreadable or cut off.
            - If the page is not readable enough to trust, reply exactly `[[vision transcription failed]]`.
            """
        ),
    ),
    PromptVariant(
        slug="edge-first",
        title="Edge First",
        prompt=textwrap.dedent(
            """\
            Read this single Kindle page image and transcribe it.

            Important:
            - Start by reading the text nearest the right image edge. Then continue column by column toward the left.
            - Do not drop the first column even if it sits very close to the border.
            - The goal is a usable full-page transcript, not a conservative OCR report.

            Rules:
            - Output only the transcript.
            - Japanese vertical text should be reordered into natural reading order.
            - If a few characters are uncertain, guess from context.
            - Only use `[[partial vision transcription]]` if substantial text is missing, not for minor uncertainty.
            - If the page is not readable enough to trust, reply exactly `[[vision transcription failed]]`.
            """
        ),
    ),
    PromptVariant(
        slug="literal-best-effort",
        title="Literal Best Effort",
        prompt=textwrap.dedent(
            """\
            Produce the most complete literal transcription you can for this one Kindle page.

            Rules:
            - Output only the page text.
            - Treat this as a best-effort recovery task. Missing a few edge characters is worse than making a reasonable contextual guess.
            - Read vertical Japanese in the correct column order from right to left.
            - Preserve section headers such as chapter or subsection labels.
            - Do not emit `[[partial vision transcription]]` unless at least one full vertical column or a clearly meaningful text span is unreadable.
            - If the page is not readable enough to trust, reply exactly `[[vision transcription failed]]`.
            """
        ),
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a prompt sweep for Codex vision on a fixed Kindle page image.")
    parser.add_argument("--image", required=True, help="Input image path.")
    parser.add_argument(
        "--output-dir",
        help="Directory for outputs. Defaults to kindle/prompt-sweeps/<image-stem>/",
    )
    parser.add_argument(
        "--codex-workdir",
        default=str(DEFAULT_WORKDIR),
        help="Working directory passed to `codex exec -C`.",
    )
    parser.add_argument(
        "--reasoning-effort",
        default="medium",
        help="Reasoning effort override for Codex.",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=900,
        help="Timeout for each prompt variant.",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def score_text(text: str) -> dict:
    normalized = normalize_text(text)
    return {
        "length": len(normalized),
        "is_partial": text.startswith("[[partial vision transcription]]"),
        "is_failed": text == "[[vision transcription failed]]",
    }


def run_variant(
    *,
    variant: PromptVariant,
    image_path: pathlib.Path,
    output_dir: pathlib.Path,
    workdir: pathlib.Path,
    reasoning_effort: str,
    timeout_sec: int,
) -> dict:
    output_path = output_dir / f"{variant.slug}.txt"
    log_path = output_dir / f"{variant.slug}.log"
    prompt_path = output_dir / f"{variant.slug}.prompt.md"
    prompt_path.write_text(variant.prompt, encoding="utf-8")

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
            input=variant.prompt,
            text=True,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            timeout=timeout_sec,
            check=False,
        )

    if completed.returncode != 0:
        text = "[[vision transcription failed]]"
        output_path.write_text(text + "\n", encoding="utf-8")
    else:
        text = output_path.read_text(encoding="utf-8").strip() or "[[vision transcription failed]]"
        output_path.write_text(text + "\n", encoding="utf-8")

    scores = score_text(text)
    return {
        "slug": variant.slug,
        "title": variant.title,
        "output_path": str(output_path),
        "log_path": str(log_path),
        "prompt_path": str(prompt_path),
        "returncode": completed.returncode,
        **scores,
    }


def main() -> int:
    args = parse_args()
    image_path = pathlib.Path(args.image).expanduser().resolve()
    if not image_path.exists():
        raise SystemExit(f"Image not found: {image_path}")

    output_dir = (
        pathlib.Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else (ROOT / "prompt-sweeps" / image_path.stem).resolve()
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for variant in PROMPT_VARIANTS:
        result = run_variant(
            variant=variant,
            image_path=image_path,
            output_dir=output_dir,
            workdir=pathlib.Path(args.codex_workdir).expanduser().resolve(),
            reasoning_effort=args.reasoning_effort,
            timeout_sec=args.timeout_sec,
        )
        results.append(result)
        print(
            f"{variant.slug}: returncode={result['returncode']} partial={result['is_partial']} "
            f"failed={result['is_failed']} length={result['length']}",
            flush=True,
        )

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    readme_lines = [
        "# Prompt sweep results",
        "",
        f"- image: `{image_path}`",
        "",
    ]
    for result in results:
        readme_lines.extend(
            [
                f"## {result['slug']}",
                "",
                f"- returncode: `{result['returncode']}`",
                f"- partial: `{result['is_partial']}`",
                f"- failed: `{result['is_failed']}`",
                f"- normalized_length: `{result['length']}`",
                f"- prompt: `{pathlib.Path(result['prompt_path']).name}`",
                f"- output: `{pathlib.Path(result['output_path']).name}`",
                f"- log: `{pathlib.Path(result['log_path']).name}`",
                "",
            ]
        )
    (output_dir / "README.md").write_text("\n".join(readme_lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
