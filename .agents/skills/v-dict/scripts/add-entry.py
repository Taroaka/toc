#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DICT_PATH = REPO_ROOT / "config" / "tts-pronunciation-aliases.tsv"


def parse_pair_token(token: str) -> tuple[str, str]:
    raw = token.strip()
    for separator in ("=>", "\t", "="):
        if separator in raw:
            surface, reading = raw.split(separator, 1)
            return clean_field(surface), clean_field(reading)
    raise ValueError(f"cannot parse entry: {token!r}")


def clean_field(value: str) -> str:
    text = value.strip()
    if not text:
        raise ValueError("surface and reading must be non-empty")
    if "\n" in text or "\r" in text or "\t" in text:
        raise ValueError("surface and reading must not contain newlines or tabs")
    return text


def requested_entries(args: argparse.Namespace) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    if args.surface or args.reading:
        if not args.surface or not args.reading:
            raise ValueError("--surface and --reading must be used together")
        entries.append((clean_field(args.surface), clean_field(args.reading)))
    for raw in args.entry or []:
        entries.append(parse_pair_token(raw))
    if args.pairs:
        if len(args.pairs) == 1:
            entries.append(parse_pair_token(args.pairs[0]))
        elif len(args.pairs) % 2 == 0:
            iterator = iter(args.pairs)
            entries.extend((clean_field(surface), clean_field(reading)) for surface, reading in zip(iterator, iterator))
        else:
            raise ValueError("positional entries must be surface reading pairs")
    if not entries:
        raise ValueError("no pronunciation entries provided")
    return entries


def default_dict_path() -> Path:
    configured = os.environ.get("TOC_TTS_PRONUNCIATION_ALIAS_FILE")
    return Path(configured).expanduser() if configured else DEFAULT_DICT_PATH


def read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8").splitlines()


def split_dict_line(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if "\t" in line:
        surface, reading = line.split("\t", 1)
    elif "=>" in line:
        surface, reading = line.split("=>", 1)
    else:
        return None
    surface = surface.strip()
    reading = reading.strip()
    if not surface or not reading:
        return None
    return surface, reading


def apply_entries(lines: list[str], entries: list[tuple[str, str]]) -> tuple[list[str], dict[str, list[dict[str, str]]]]:
    output = list(lines)
    summary: dict[str, list[dict[str, str]]] = {"added": [], "updated": [], "unchanged": []}
    seen_surfaces: set[str] = set()

    for surface, reading in entries:
        found_index: int | None = None
        previous_reading = ""
        for index, line in enumerate(output):
            parsed = split_dict_line(line)
            if parsed is None:
                continue
            current_surface, current_reading = parsed
            if current_surface != surface:
                continue
            if found_index is None:
                found_index = index
                previous_reading = current_reading
            elif current_surface not in seen_surfaces:
                output[index] = ""

        seen_surfaces.add(surface)
        item = {"surface": surface, "reading": reading}
        if found_index is None:
            output.append(f"{surface}\t{reading}")
            summary["added"].append(item)
        elif previous_reading == reading:
            summary["unchanged"].append(item)
        else:
            output[found_index] = f"{surface}\t{reading}"
            item["previous_reading"] = previous_reading
            summary["updated"].append(item)

    cleaned = []
    blank_pending = False
    for line in output:
        if line == "":
            blank_pending = True
            continue
        if blank_pending and cleaned and cleaned[-1] != "":
            cleaned.append("")
        cleaned.append(line)
        blank_pending = False
    return cleaned, summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Add or update ToC TTS pronunciation aliases.")
    parser.add_argument("pairs", nargs="*", help="surface reading pairs, or one token such as surface=reading")
    parser.add_argument("--surface", default="")
    parser.add_argument("--reading", default="")
    parser.add_argument("--entry", action="append", default=None, help="Entry such as surface=reading or surface=>reading")
    parser.add_argument("--dict", dest="dict_path", default="", help="Dictionary path. Defaults to TOC_TTS_PRONUNCIATION_ALIAS_FILE or config/tts-pronunciation-aliases.tsv.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        entries = requested_entries(args)
        path = Path(args.dict_path).expanduser() if args.dict_path else default_dict_path()
        if not path.is_absolute():
            path = REPO_ROOT / path
        lines = read_lines(path)
        next_lines, summary = apply_entries(lines, entries)
        if not args.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(next_lines).rstrip() + "\n", encoding="utf-8")
        print(json.dumps({"path": str(path), "dry_run": args.dry_run, **summary}, ensure_ascii=False, indent=2))
    except Exception as exc:
        raise SystemExit(f"ERROR: {exc}") from exc


if __name__ == "__main__":
    main()
