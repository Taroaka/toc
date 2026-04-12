#!/usr/bin/env python3
"""Validate fixed p-slot workflow contract consistency."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.run_index import SLOT_BY_CODE


SLOT_CODE_PATTERN = re.compile(r"`(p\d{3})`")
REQUIRED_GENERIC_KEYS = (
    "slot.pXXX.status",
    "slot.pXXX.requirement",
    "slot.pXXX.skip_reason",
    "slot.pXXX.note",
)
ALLOWED_TOP_LEVEL_CODES = {"p000", "p100", "p200", "p300", "p400", "p500", "p600", "p700", "p800", "p900"}


def extract_slot_codes(text: str) -> set[str]:
    return set(SLOT_CODE_PATTERN.findall(text))


def expected_fine_slots() -> set[str]:
    return {code for code in SLOT_BY_CODE if code not in {"p000", "p010", "p020", "p030", "p040", "p050"}}


def sorted_slot_codes(codes: set[str]) -> list[str]:
    return sorted(codes, key=lambda code: int(code[1:]))


def validate_slot_doc(label: str, codes: set[str], expected: set[str], errors: list[str]) -> None:
    missing = sorted_slot_codes(expected - codes)
    unexpected = sorted_slot_codes({code for code in codes if code not in expected and code not in ALLOWED_TOP_LEVEL_CODES})
    if missing:
        errors.append(f"{label} is missing fixed slot codes: " + ", ".join(missing))
    if unexpected:
        errors.append(f"{label} contains unknown or stale slot codes: " + ", ".join(unexpected))


def validate(root: Path) -> list[str]:
    errors: list[str] = []

    system_arch = root / "docs/system-architecture.md"
    how_to_run = root / "docs/how-to-run.md"
    data_contracts = root / "docs/data-contracts.md"
    state_schema = root / "workflow/state-schema.txt"
    root_pointer = root / "docs/root-pointer-guide.md"

    for path in (system_arch, how_to_run, data_contracts, state_schema, root_pointer):
        if not path.exists():
            errors.append(f"Missing required contract doc: {path.relative_to(root)}")
            return errors

    expected = expected_fine_slots()
    system_codes = extract_slot_codes(system_arch.read_text(encoding="utf-8"))
    how_to_run_codes = extract_slot_codes(how_to_run.read_text(encoding="utf-8"))
    validate_slot_doc("docs/system-architecture.md", system_codes, expected, errors)
    validate_slot_doc("docs/how-to-run.md", how_to_run_codes, expected, errors)

    docs_with_generic_keys = {
        "docs/data-contracts.md": data_contracts.read_text(encoding="utf-8"),
        "workflow/state-schema.txt": state_schema.read_text(encoding="utf-8"),
    }
    for label, text in docs_with_generic_keys.items():
        for key in REQUIRED_GENERIC_KEYS:
            if key not in text:
                errors.append(f"{label} is missing generic slot key: {key}")

    root_pointer_text = root_pointer.read_text(encoding="utf-8")
    if "fixed slot workflow" not in root_pointer_text:
        errors.append("docs/root-pointer-guide.md should mention the fixed slot workflow")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate fixed p-slot workflow contract.")
    parser.add_argument("--root", default=".", help="Repository root (default: current directory)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors = validate(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Slot contract valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
