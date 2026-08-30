"""Deterministic review-mode binding shared by runners and validators."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.world_walk_source import read_regular_file_nofollow
from toc.harness import parse_state_file
from toc.run_root_binding import current_run_root_binding


CREATE_INPUT_RELPATH = Path("logs/orchestration/create_input.json")
CREATE_INPUT_SCHEMA_VERSION = "toc.create_input.v1"


def review_mode_is_bound_preapproved(run_dir: Path) -> bool:
    """Return true only when state and the immutable create input agree."""

    state = parse_state_file(run_dir / "state.txt")
    state_mode = str(state.get("runtime.review_mode") or "").strip().lower()
    state_policy = str(
        state.get("runtime.review_policy") or ""
    ).strip().lower()
    if state_mode != "preapproved" and state_policy != "preapproved":
        return False
    if state_mode != "preapproved" or state_policy != "preapproved":
        raise RuntimeError(
            "preapproved review mode state is internally inconsistent"
        )
    binding = current_run_root_binding()
    try:
        create_input = json.loads(
            read_regular_file_nofollow(
                run_dir,
                CREATE_INPUT_RELPATH,
                expected_root_identity=(
                    binding.identity if binding is not None else None
                ),
            ).decode("utf-8")
        )
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "preapproved review mode requires a readable create_input contract"
        ) from exc
    if (
        not isinstance(create_input, dict)
        or create_input.get("schema_version")
        != CREATE_INPUT_SCHEMA_VERSION
        or create_input.get("review_mode") != "preapproved"
    ):
        raise RuntimeError(
            "preapproved review mode is not bound to create_input.json"
        )
    return True
