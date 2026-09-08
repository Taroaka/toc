"""Structural video output checks.

Only file existence, ffprobe duration, optional narration-list paths, and
known render status values are checked here. No video review status or score is
required.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .pipeline import (
    _probe_duration,
    append_video_checks,
    check_video_scene_series,
    check_video_single,
)


__all__ = [
    "_probe_duration",
    "append_video_checks",
    "check_video_scene_series",
    "check_video_single",
]
