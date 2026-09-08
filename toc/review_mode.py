"""Compatibility helpers for clients that still send a review mode.

Production no longer has separate ``standard`` and ``preapproved`` paths.
Older state files and create payloads can still contain those values, but they
must not alter orchestration or manufacture an approval certificate.
"""

from __future__ import annotations

from pathlib import Path


CREATE_INPUT_RELPATH = Path("logs/orchestration/create_input.json")
CREATE_INPUT_SCHEMA_VERSION = "toc.create_input.v1"


def review_mode_is_bound_preapproved(run_dir: Path) -> bool:
    """Return ``False`` for every run; modes are legacy input only.

    The function remains importable for migration code.  Production callers
    should not branch on it, and no caller can use it to bypass validation or
    create a synthetic passed report.
    """

    del run_dir
    return False


__all__ = [
    "CREATE_INPUT_RELPATH",
    "CREATE_INPUT_SCHEMA_VERSION",
    "review_mode_is_bound_preapproved",
]
