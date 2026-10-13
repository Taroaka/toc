#!/usr/bin/env python3
"""Read or update a single cut's shot direction through the server service."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi import HTTPException

from server import cut_direction_api as service


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or edit shot direction for one ToC manifest cut."
    )
    run = parser.add_mutually_exclusive_group(required=True)
    run.add_argument("--run-id", help="run directory name under the configured output root")
    run.add_argument("--run-dir", type=Path, help="path to one run directory under the configured output root")
    parser.add_argument("--item-id", help="manifest cut selector, for example scene3_cut2")
    parser.add_argument("--expected-revision", help="GET revision required for a write")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-json", help="plan JSON text or a path to a JSON file")
    mode.add_argument("--instruction", help="natural-language correction for the selected cut")
    return parser


def _run_id(args: argparse.Namespace) -> str:
    api = service.app()
    if args.run_id:
        return args.run_id
    run_dir = args.run_dir.expanduser().resolve(strict=True)
    root = Path(api.output_root(api.ROOT)).resolve(strict=True)
    try:
        relative = run_dir.relative_to(root)
    except ValueError as exc:
        raise ValueError("--run-dir must be directly inside the configured output root") from exc
    if len(relative.parts) != 1 or relative.name in {"", ".", ".."}:
        raise ValueError("--run-dir must name exactly one run directory under the configured output root")
    return relative.name


def _plan_value(argument: str) -> dict[str, Any]:
    path = Path(argument).expanduser()
    content = path.read_text(encoding="utf-8") if path.is_file() else argument
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("--plan-json must contain a JSON object")
    return value


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    run_id = _run_id(args)
    if args.plan_json is not None or args.instruction is not None:
        if not args.item_id:
            raise ValueError("--item-id is required when saving a shot plan")
        if not args.expected_revision:
            raise ValueError("--expected-revision is required when saving a shot plan")
        request = service.CutDirectionRequest(
            run_id=run_id,
            item_id=args.item_id,
            expected_revision=args.expected_revision,
            plan=_plan_value(args.plan_json) if args.plan_json is not None else None,
            instruction=args.instruction,
        )
        return await service.save_cut_direction(request)

    result = await service.get_cut_direction(run_id)
    if args.item_id:
        result["scenes"] = [
            {
                **scene,
                "cuts": [cut for cut in scene.get("cuts", []) if cut.get("id") == args.item_id],
            }
            for scene in result["scenes"]
            if any(cut.get("id") == args.item_id for cut in scene.get("cuts", []))
        ]
        if not result["scenes"]:
            raise ValueError(f"cut not found: {args.item_id}")
    return result


def main() -> int:
    args = _parser().parse_args()
    try:
        result = asyncio.run(_run(args))
    except HTTPException as exc:
        print(json.dumps({"status": "error", "status_code": exc.status_code, "detail": exc.detail}, ensure_ascii=False))
        return 1
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "error", "detail": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
