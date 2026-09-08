"""Production state and fixed-slot contract helpers.

The review loop used to occupy fixed slots in the run workflow.  Those slots
remain meaningful in historical ``state.txt`` files, but they are no longer
part of the active production contract.  Keep the list in one small module so
state readers, progress projections, and the UI agree on what to ignore.
"""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


RETIRED_REVIEW_SLOTS: frozenset[str] = frozenset(
    {
        "p130",
        "p230",
        "p320",
        "p430",
        "p435",
        "p540",
        "p630",
        "p640",
        "p720",
        "p820",
        "p850",
        "p930",
    }
)


def normalize_slot_code(value: object) -> str:
    """Return a canonical fixed-slot code for comparisons."""

    return str(value or "").strip().lower()


def is_retired_review_slot(value: object) -> bool:
    """Whether *value* names a review-only slot retired from production."""

    return normalize_slot_code(value) in RETIRED_REVIEW_SLOTS


def active_slot_codes(codes: Mapping[str, Any] | set[str] | list[str] | tuple[str, ...]) -> set[str]:
    """Filter retired review slots from a slot-code collection."""

    values = codes.keys() if isinstance(codes, Mapping) else codes
    return {str(code) for code in values if not is_retired_review_slot(code)}


_RETIRED_SLOT_STATE_KEY = re.compile(r"^slot\.(p\d{3})\.")


def is_retired_slot_state_key(key: object) -> bool:
    """Whether a dotted state key belongs to one retired slot."""

    match = _RETIRED_SLOT_STATE_KEY.match(str(key or "").strip().lower())
    return bool(match and is_retired_review_slot(match.group(1)))


def filter_active_slot_state(state: Mapping[str, str]) -> dict[str, str]:
    """Return state with historical retired-slot keys omitted.

    This is intentionally a read-time projection.  Callers must continue to
    preserve the original append-only state history.
    """

    return {
        str(key): str(value)
        for key, value in state.items()
        if not is_retired_slot_state_key(key)
    }


__all__ = [
    "RETIRED_REVIEW_SLOTS",
    "active_slot_codes",
    "filter_active_slot_state",
    "is_retired_review_slot",
    "is_retired_slot_state_key",
    "normalize_slot_code",
]
