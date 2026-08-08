#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import stat


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Exec a command after entering an inherited directory fd.",
    )
    parser.add_argument("--fd", required=True, type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a command is required after --")
    opened = os.fstat(args.fd)
    if not stat.S_ISDIR(opened.st_mode):
        parser.error("--fd must name an inherited directory descriptor")
    os.fchdir(args.fd)
    os.close(args.fd)
    os.execvpe(command[0], command, os.environ)
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
