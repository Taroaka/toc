#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.run_index import write_run_index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build p000_index.md for a run directory.")
    parser.add_argument("--run-dir", required=True, help="Path to output/<topic>_<timestamp>/")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    output = write_run_index(run_dir)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
