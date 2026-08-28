#!/usr/bin/env python3
"""Prepare/apply/recover a checkpointed p400 authoring rebuild.

The prepare command accepts already-built candidate bytes from ``--candidate-dir``.
It never calls a provider and never overwrites canonical run artifacts.  Apply
only consumes the exact bytes recorded in the staged plan.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.p400_rebuild import (  # noqa: E402
    CandidateBundle,
    P400RebuildError,
    REQUIRED_CANDIDATE_PATHS,
    apply_p400_rebuild,
    load_p400_rebuild_plan,
    prepare_p400_rebuild,
    recover_p400_rebuild,
)
from scripts.world_walk_source import (  # noqa: E402
    directory_identity_nofollow,
    read_regular_file_nofollow,
)


_MAX_CANDIDATE_FILES = 256
_MAX_CANDIDATE_FILE_BYTES = 32 * 1024 * 1024
_MAX_CANDIDATE_TOTAL_BYTES = 128 * 1024 * 1024
_MAX_CANDIDATE_DEPTH = 8


def _candidate_bytes(candidate_dir: Path) -> dict[str, bytes]:
    if candidate_dir.is_symlink() or not candidate_dir.is_dir():
        raise P400RebuildError("candidate directory must be a real directory")
    identity = directory_identity_nofollow(candidate_dir)
    artifacts: dict[str, bytes] = {}
    total_bytes = 0
    for current_root, directories, files in os.walk(
        candidate_dir,
        topdown=True,
        followlinks=False,
    ):
        current = Path(current_root)
        relative_root = current.relative_to(candidate_dir)
        if len(relative_root.parts) > _MAX_CANDIDATE_DEPTH:
            raise P400RebuildError("candidate directory nesting is too deep")
        for directory in list(directories):
            target = current / directory
            if stat.S_ISLNK(target.lstat().st_mode):
                raise P400RebuildError(
                    f"candidate directory contains a symlink: {target.relative_to(candidate_dir)}"
                )
        for filename in files:
            path = current / filename
            relative = path.relative_to(candidate_dir).as_posix()
            lexical = path.lstat()
            if stat.S_ISLNK(lexical.st_mode):
                raise P400RebuildError(
                    f"candidate directory contains a symlink: {relative}"
                )
            if not stat.S_ISREG(lexical.st_mode):
                raise P400RebuildError(
                    f"candidate artifact is not a regular file: {relative}"
                )
            if relative in {"plan.json", "publish.journal.json"}:
                continue
            if len(artifacts) >= _MAX_CANDIDATE_FILES:
                raise P400RebuildError("candidate artifact count exceeds the limit")
            if lexical.st_size > _MAX_CANDIDATE_FILE_BYTES:
                raise P400RebuildError(f"candidate artifact is too large: {relative}")
            try:
                data = read_regular_file_nofollow(
                    candidate_dir,
                    relative,
                    expected_root_identity=identity,
                )
            except Exception as exc:
                raise P400RebuildError(
                    f"could not safely read candidate artifact: {relative}"
                ) from exc
            total_bytes += len(data)
            if total_bytes > _MAX_CANDIDATE_TOTAL_BYTES:
                raise P400RebuildError("candidate artifact bytes exceed the limit")
            artifacts[relative] = data
    missing = sorted(set(REQUIRED_CANDIDATE_PATHS) - set(artifacts))
    if missing:
        raise P400RebuildError(
            "candidate directory is missing required artifacts: " + ", ".join(missing)
        )
    return artifacts


def _print_plan(plan) -> None:
    print(json.dumps(plan.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Checkpointed p400 scene-authoring rebuild transaction."
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--candidate-dir", type=Path)
    parser.add_argument("--generation-id", default="")
    parser.add_argument("--checkpoint-id", default="")
    parser.add_argument("--plan-token", default="")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--recover",
        choices=("rollback", "complete"),
        help="Recover an interrupted checkpoint journal.",
    )
    args = parser.parse_args(argv)

    try:
        if args.recover:
            if not args.checkpoint_id:
                parser.error("--recover requires --checkpoint-id")
            checkpoint = recover_p400_rebuild(
                args.run_dir,
                args.checkpoint_id,
                action=args.recover,
            )
            print(json.dumps({"checkpoint_dir": str(checkpoint), "action": args.recover}))
            return 0

        if args.apply:
            if args.candidate_dir is not None:
                parser.error("--candidate-dir is only valid during prepare")
            if not args.generation_id or not args.checkpoint_id or not args.plan_token:
                parser.error(
                    "--apply requires --generation-id, --checkpoint-id, and --plan-token"
                )
            plan = load_p400_rebuild_plan(args.run_dir, args.generation_id)
            if plan.checkpoint_id != args.checkpoint_id:
                raise P400RebuildError("checkpoint id does not match staged plan")
            checkpoint = apply_p400_rebuild(plan, plan_token=args.plan_token)
            print(json.dumps({"checkpoint_dir": str(checkpoint), "phase": "completed"}))
            return 0

        if args.candidate_dir is None:
            parser.error("prepare requires --candidate-dir")
        bundle = CandidateBundle(
            artifacts=_candidate_bytes(args.candidate_dir),
        )
        plan = prepare_p400_rebuild(
            repo_root=args.repo_root,
            run_dir=args.run_dir,
            checkpoint_id=args.checkpoint_id or None,
            generation_id=args.generation_id or None,
            candidate_builder=lambda _context: bundle,
        )
        _print_plan(plan)
        return 0
    except P400RebuildError as exc:
        print(f"p400 rebuild failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
