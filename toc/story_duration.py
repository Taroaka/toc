"""Shared planning and lower-bound duration rules for ToC story runs."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable

from toc.immersive_manifest import is_non_renderable_manifest_node

DEFAULT_TARGET_DURATION_SECONDS = 300
MIN_TARGET_DURATION_SECONDS = 300
MAX_TARGET_DURATION_SECONDS = 1200
MINIMUM_EFFECTIVE_RATIO = 0.80
MINIMUM_NARRATION_RATIO = 0.70
MAX_SECONDS_PER_SCENE = 40
MAX_SECONDS_PER_CUT = 12


@dataclass(frozen=True)
class StoryDurationPlan:
    target_seconds: int
    minimum_scene_count: int
    minimum_cut_count: int
    minimum_narration_seconds: int
    minimum_effective_seconds: float

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True)
class DurationAudit:
    target_seconds: int
    minimum_seconds: float
    actual_seconds: float
    ratio: float
    measurement_layer: str
    passed: bool

    @property
    def status(self) -> str:
        return "passed" if self.passed else "changes_requested"

    def to_dict(self) -> dict[str, int | float | str | bool]:
        return {**asdict(self), "status": self.status}


@dataclass(frozen=True)
class ManifestRuntimeMeasurement:
    """Measured audio/video timelines for a renderable manifest.

    Audio and video are parallel timelines. They are intentionally reported
    separately so render-unit video durations are never added to their source
    cut durations. The current renderer uses the shorter timeline as the
    effective runtime.
    """

    spoken_audio_seconds: float
    intentional_silence_seconds: float
    audio_timeline_seconds: float
    video_timeline_seconds: float
    effective_seconds: float
    video_timeline_source: str
    complete: bool
    missing_items: tuple[str, ...]
    invalid_items: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MediaDurationProbe = Callable[[Path], Any]


def _selector_value(value: Any, fallback: str) -> str:
    text = str(value if value is not None else "").strip()
    return text or fallback


def _is_deleted(node: dict[str, Any]) -> bool:
    return str(node.get("cut_status") or node.get("status") or "").strip().lower() == "deleted"


def _is_non_renderable_reference(node: dict[str, Any]) -> bool:
    return is_non_renderable_manifest_node(node) and not _is_deleted(node)


def _positive_seconds(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(seconds) or seconds <= 0:
        return None
    return seconds


def _video_duration(node: dict[str, Any]) -> tuple[float | None, str]:
    video_generation = node.get("video_generation")
    if not isinstance(video_generation, dict) or "duration_seconds" not in video_generation:
        return None, "missing"
    duration = _positive_seconds(video_generation.get("duration_seconds"))
    return (duration, "ok") if duration is not None else (None, "invalid")


def _confirmed_silence(narration: dict[str, Any]) -> bool:
    contract = narration.get("silence_contract")
    if not isinstance(contract, dict):
        return False
    return (
        contract.get("intentional") is True
        and contract.get("confirmed_by_human") is True
        and bool(str(contract.get("kind") or "").strip())
        and bool(str(contract.get("reason") or "").strip())
    )


def measure_manifest_runtime(
    manifest: dict[str, Any],
    *,
    base_dir: Path,
    probe: MediaDurationProbe,
) -> ManifestRuntimeMeasurement:
    """Measure a manifest without performing filesystem or process I/O itself.

    ``probe`` receives each resolved spoken-audio path and returns its actual
    duration in seconds. Confirmed intentional silence is measured from that
    cut's explicit ``video_generation.duration_seconds``. For each scene,
    render units replace cut video durations when present.
    """

    missing: list[str] = []
    invalid: list[str] = []
    spoken_audio_seconds = 0.0
    intentional_silence_seconds = 0.0
    video_timeline_seconds = 0.0
    audio_item_count = 0
    video_item_count = 0
    video_sources: set[str] = set()

    scenes = manifest.get("scenes") if isinstance(manifest, dict) else None
    if not isinstance(scenes, list) or not scenes:
        missing.append("manifest:scenes")
        scenes = []

    for scene_index, scene in enumerate(scenes):
        if (
            not isinstance(scene, dict)
            or _is_deleted(scene)
            or _is_non_renderable_reference(scene)
        ):
            continue
        scene_id = _selector_value(scene.get("scene_id"), str(scene_index + 1))
        raw_cuts = scene.get("cuts")
        cuts = [
            cut
            for cut in raw_cuts
            if isinstance(cut, dict)
            and not _is_deleted(cut)
            and not _is_non_renderable_reference(cut)
        ] if isinstance(raw_cuts, list) else []
        if isinstance(raw_cuts, list) and raw_cuts and not cuts:
            continue
        nodes = cuts or [scene]

        for cut_index, node in enumerate(nodes):
            cut_id = _selector_value(node.get("cut_id"), str(cut_index + 1)) if cuts else ""
            selector = f"scene{scene_id}_cut{cut_id}" if cuts else f"scene{scene_id}"
            audio_item_count += 1
            audio = node.get("audio")
            narration = audio.get("narration") if isinstance(audio, dict) else None
            if not isinstance(narration, dict):
                missing.append(f"{selector}:narration")
                continue

            tool = str(narration.get("tool") or "").strip().lower()
            if tool == "silent":
                if not _confirmed_silence(narration):
                    invalid.append(f"{selector}:silence_contract")
                    continue
                silence_seconds, silence_status = _video_duration(node)
                if silence_seconds is None:
                    issue = "silence_duration"
                    (missing if silence_status == "missing" else invalid).append(f"{selector}:{issue}")
                    continue
                intentional_silence_seconds += silence_seconds
                continue

            output = str(narration.get("output") or "").strip()
            if not output:
                missing.append(f"{selector}:audio_output")
                continue
            output_path = Path(output)
            resolved_path = output_path if output_path.is_absolute() else Path(base_dir) / output_path
            try:
                probed_seconds = _positive_seconds(probe(resolved_path))
            except Exception:
                probed_seconds = None
            if probed_seconds is None:
                invalid.append(f"{selector}:audio_duration")
                continue
            spoken_audio_seconds += probed_seconds

        raw_render_units = scene.get("render_units")
        render_units = (
            [
                unit
                for unit in raw_render_units
                if isinstance(unit, dict)
                and not _is_deleted(unit)
                and not _is_non_renderable_reference(unit)
            ]
            if isinstance(raw_render_units, list)
            else []
        )
        video_nodes: list[tuple[str, dict[str, Any]]]
        if render_units:
            video_sources.add("render_units")
            video_nodes = [
                (f"scene{scene_id}_unit{_selector_value(unit.get('unit_id'), str(unit_index + 1))}", unit)
                for unit_index, unit in enumerate(render_units)
            ]
        else:
            video_sources.add("cuts")
            video_nodes = []
            for cut_index, node in enumerate(nodes):
                cut_id = _selector_value(node.get("cut_id"), str(cut_index + 1)) if cuts else ""
                selector = f"scene{scene_id}_cut{cut_id}" if cuts else f"scene{scene_id}"
                video_nodes.append((selector, node))

        for selector, node in video_nodes:
            video_item_count += 1
            duration, status = _video_duration(node)
            if duration is None:
                issue = f"{selector}:video_duration"
                (missing if status == "missing" else invalid).append(issue)
                continue
            video_timeline_seconds += duration

    if audio_item_count == 0 and "manifest:scenes" not in missing:
        missing.append("manifest:audio_timeline")
    if video_item_count == 0 and "manifest:scenes" not in missing:
        missing.append("manifest:video_timeline")

    audio_timeline_seconds = spoken_audio_seconds + intentional_silence_seconds
    effective_seconds = min(audio_timeline_seconds, video_timeline_seconds)
    if not video_sources:
        video_timeline_source = "none"
    elif len(video_sources) == 1:
        video_timeline_source = next(iter(video_sources))
    else:
        video_timeline_source = "mixed"

    return ManifestRuntimeMeasurement(
        spoken_audio_seconds=spoken_audio_seconds,
        intentional_silence_seconds=intentional_silence_seconds,
        audio_timeline_seconds=audio_timeline_seconds,
        video_timeline_seconds=video_timeline_seconds,
        effective_seconds=effective_seconds,
        video_timeline_source=video_timeline_source,
        complete=not missing and not invalid and audio_item_count > 0 and video_item_count > 0,
        missing_items=tuple(dict.fromkeys(missing)),
        invalid_items=tuple(dict.fromkeys(invalid)),
    )


def normalize_target_duration(value: Any = None) -> int:
    """Return a validated integer target, defaulting missing values to five minutes."""

    if value is None:
        target = DEFAULT_TARGET_DURATION_SECONDS
    elif isinstance(value, bool) or isinstance(value, float):
        raise ValueError("target_duration_seconds must be an integer")
    elif isinstance(value, int):
        target = value
    elif isinstance(value, str) and value.strip().isdigit():
        target = int(value.strip())
    else:
        raise ValueError("target_duration_seconds must be an integer")

    if not MIN_TARGET_DURATION_SECONDS <= target <= MAX_TARGET_DURATION_SECONDS:
        raise ValueError(
            f"target_duration_seconds must be between {MIN_TARGET_DURATION_SECONDS} and "
            f"{MAX_TARGET_DURATION_SECONDS}"
        )
    return target


def build_duration_plan(target_duration_seconds: Any = None) -> StoryDurationPlan:
    target = normalize_target_duration(target_duration_seconds)
    return StoryDurationPlan(
        target_seconds=target,
        minimum_scene_count=math.ceil(target / MAX_SECONDS_PER_SCENE),
        minimum_cut_count=math.ceil(target / MAX_SECONDS_PER_CUT),
        minimum_narration_seconds=math.ceil(target * MINIMUM_NARRATION_RATIO),
        minimum_effective_seconds=target * MINIMUM_EFFECTIVE_RATIO,
    )


def audit_duration(
    *,
    target_seconds: Any,
    actual_seconds: Any,
    measurement_layer: str,
) -> DurationAudit:
    target = normalize_target_duration(target_seconds)
    layer = str(measurement_layer or "").strip()
    if not layer:
        raise ValueError("measurement_layer is required")
    if isinstance(actual_seconds, bool):
        raise ValueError("actual_seconds must be a finite non-negative number")
    try:
        actual = float(actual_seconds)
    except (TypeError, ValueError) as exc:
        raise ValueError("actual_seconds must be a finite non-negative number") from exc
    if not math.isfinite(actual) or actual < 0:
        raise ValueError("actual_seconds must be a finite non-negative number")

    minimum = target * MINIMUM_EFFECTIVE_RATIO
    return DurationAudit(
        target_seconds=target,
        minimum_seconds=minimum,
        actual_seconds=actual,
        ratio=actual / target,
        measurement_layer=layer,
        passed=actual >= minimum,
    )
