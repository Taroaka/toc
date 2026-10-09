#!/usr/bin/env python3
"""Mix the immutable p860 selections frozen by p910, before final video muxing."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from toc.sound_design import mix_audio


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--narration-list", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    mix_audio(json.loads(args.plan.read_text()), args.narration_list, args.out)


if __name__ == "__main__":
    main()
