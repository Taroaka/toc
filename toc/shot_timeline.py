"""Runtime validation for projected shot schedules."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_CEILING
import re
from typing import Any


SHOT_DIRECTION_SCHEMA = "shot_direction_v1"
_SHOT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$")
_TIMELINE_TOLERANCE = Decimal("0.000001")
_KLING_V3_MODEL = "kling-video/v3.0/std/image-to-video"


class ShotTimelineError(ValueError):
    """A projected shot timeline or provider request is inconsistent."""


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _number(value: Any, *, selector: str, field: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise ShotTimelineError(f"{selector}: shot {field} must be a finite number")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ShotTimelineError(f"{selector}: shot {field} must be a finite number") from None
    if not parsed.is_finite():
        raise ShotTimelineError(f"{selector}: shot {field} must be a finite number")
    return parsed


def _parent_duration(cut: dict[str, Any], *, selector: str) -> Decimal:
    from toc.shot_direction import parent_duration_seconds

    try:
        value = parent_duration_seconds(cut)
    except ValueError as exc:
        raise ShotTimelineError(f"{selector}: {exc}") from exc
    duration = _number(value, selector=selector, field="parent duration")
    if duration <= 0:
        raise ShotTimelineError(f"{selector}: parent cut duration must be positive")
    return duration


def _is_kling_v3(tool: str, model: str) -> bool:
    normalized_tool = re.sub(r"[\s-]+", "_", tool.strip().lower())
    normalized_model = model.strip().lower()
    return normalized_tool in {
        "kling",
        "kling_3.0",
        "kling_3_0",
        "kling_3_0_omni",
        "kling_3.0_omni",
        "kling_omni",
    } or (
        normalized_tool == "higgsfield"
        and normalized_model == _KLING_V3_MODEL
    )


def validate_projected_shot_schedule(
    cut: dict[str, Any],
    *,
    parent_selector: str,
    parent_aliases: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Validate child shots and return canonical Decimal timeline bindings.

    The authoring schema permits a 1e-6 floating-point comparison tolerance.
    Provider clips remain at their declared API duration; the returned timeline
    duration is normalized to the parent cut exactly for render concatenation.
    """

    plan = cut.get("shot_plan")
    if plan is None:
        if isinstance(cut.get("shots"), list) and cut.get("shots"):
            raise ShotTimelineError(
                f"{parent_selector}: shots require shot_plan.schema_version={SHOT_DIRECTION_SCHEMA}"
            )
        return []
    if not isinstance(plan, dict) or str(plan.get("schema_version") or "") != SHOT_DIRECTION_SCHEMA:
        raise ShotTimelineError(f"{parent_selector}: unsupported shot_plan schema_version")
    raw_shots = cut.get("shots")
    if not isinstance(raw_shots, list) or not raw_shots or len(raw_shots) > 60:
        raise ShotTimelineError(f"{parent_selector}: shot plan requires 1–60 shots")
    parent_duration = _parent_duration(cut, selector=parent_selector)
    accepted_parent_selectors = set(parent_aliases or {parent_selector})
    authored_parent_selector = str(cut.get("selector") or parent_selector).strip()
    if authored_parent_selector not in accepted_parent_selectors:
        raise ShotTimelineError(f"{parent_selector}: parent cut selector is not canonical")
    parent_image = _mapping(cut.get("image_generation"))
    cursor = Decimal(0)
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    output_owners: dict[str, str] = {}

    for index, raw_shot in enumerate(raw_shots, start=1):
        if not isinstance(raw_shot, dict):
            raise ShotTimelineError(f"{parent_selector}: shots[{index}] must be a mapping")
        shot_id = str(raw_shot.get("shot_id") or "").strip()
        folded_id = shot_id.casefold()
        if not _SHOT_ID_RE.fullmatch(shot_id) or folded_id in seen_ids:
            raise ShotTimelineError(f"{parent_selector}: duplicate or invalid shot_id")
        seen_ids.add(folded_id)
        expected_selector = f"{authored_parent_selector}_shot{shot_id}"
        selector = str(raw_shot.get("selector") or expected_selector).strip()
        shot_parent_selector = str(
            raw_shot.get("parent_selector") or authored_parent_selector
        ).strip()
        if shot_parent_selector not in accepted_parent_selectors:
            raise ShotTimelineError(f"{selector}: parent_selector does not identify its canonical cut")
        if selector != f"{shot_parent_selector}_shot{shot_id}":
            raise ShotTimelineError(f"{selector}: shot selector does not match parent selector and shot_id")

        authored_start = _number(
            raw_shot.get("start_seconds"), selector=selector, field="start_seconds"
        )
        authored_duration = _number(
            raw_shot.get("duration_seconds"), selector=selector, field="duration_seconds"
        )
        if authored_duration <= 0:
            raise ShotTimelineError(f"{selector}: shot duration_seconds must be positive")
        if abs(authored_start - cursor) > _TIMELINE_TOLERANCE:
            raise ShotTimelineError(
                f"{selector}: shot schedule must be contiguous; expected start_seconds={cursor}, got {authored_start}"
            )
        if authored_duration > Decimal(15):
            raise ShotTimelineError(f"{selector}: shot exceeds 15 seconds; split this shot into multiple shots")

        image_generation = raw_shot.get("image_generation")
        video_generation = raw_shot.get("video_generation")
        if not isinstance(image_generation, dict) or not str(image_generation.get("output") or "").strip():
            raise ShotTimelineError(f"{selector}: shot image_generation.output is required")
        if not isinstance(video_generation, dict) or not str(video_generation.get("output") or "").strip():
            raise ShotTimelineError(f"{selector}: shot video_generation.output is required")
        if not isinstance(raw_shot.get("cut_contract"), dict):
            raise ShotTimelineError(f"{selector}: shot cut_contract must be a mapping")
        for output_role, output_path in (
            ("image_generation.output", image_generation.get("output")),
            ("video_generation.output", video_generation.get("output")),
        ):
            normalized_output = str(output_path or "").replace("\\", "/").casefold()
            previous_selector = output_owners.get(normalized_output)
            if previous_selector:
                raise ShotTimelineError(
                    f"{selector}: {output_role} collides with {previous_selector} on a case-insensitive filesystem"
                )
            output_owners[normalized_output] = selector
        native_audio = _mapping(video_generation.get("native_audio"))
        if str(native_audio.get("mode") or "off").strip().lower() != "off":
            raise ShotTimelineError(f"{selector}: shot video native_audio must remain off")

        raw_provider_duration = video_generation.get("duration_seconds")
        if raw_provider_duration is None or isinstance(raw_provider_duration, bool):
            raise ShotTimelineError(f"{selector}: video_generation.duration_seconds must be a positive integer")
        try:
            provider_duration = int(raw_provider_duration)
            if Decimal(str(raw_provider_duration)) != Decimal(provider_duration) or provider_duration <= 0:
                raise ValueError
        except (InvalidOperation, ValueError, TypeError, OverflowError):
            raise ShotTimelineError(f"{selector}: video_generation.duration_seconds must be a positive integer") from None
        if Decimal(provider_duration) < authored_duration:
            raise ShotTimelineError(f"{selector}: provider duration is shorter than the shot timeline duration")

        payload = _mapping(video_generation.get("api_prompt_payload"))
        binding = _mapping(payload.get("provider_request_binding"))
        execution_options = _mapping(binding.get("execution_options"))
        tool = str(video_generation.get("tool") or "kling_3_0")
        model = str(execution_options.get("model") or video_generation.get("model") or "")
        if _is_kling_v3(tool, model):
            expected_duration = max(
                3,
                int(authored_duration.to_integral_value(rounding=ROUND_CEILING)),
            )
            if provider_duration != expected_duration:
                raise ShotTimelineError(
                    f"{selector}: Kling v3 duration_seconds must be {expected_duration} for this timeline duration"
                )
        if index == 1 and str(parent_image.get("output") or "").strip() != str(image_generation.get("output") or "").strip():
            raise ShotTimelineError(f"{parent_selector}: parent image_generation.output must alias the first shot image")

        result_binding = _mapping(video_generation.get("result_state_reference"))
        result_frame = video_generation.get("result_frame")
        if result_binding.get("required") is True and not isinstance(result_frame, dict):
            raise ShotTimelineError(f"{selector}: required result_frame is missing")
        if isinstance(result_frame, dict):
            result_image = _mapping(result_frame.get("image_generation"))
            result_output = str(result_frame.get("output") or result_image.get("output") or "").strip()
            if result_binding.get("required") is True and not result_output:
                raise ShotTimelineError(f"{selector}: required result_frame.output is missing")
            if result_output and result_image.get("output") != result_output:
                raise ShotTimelineError(f"{selector}: result_frame output must match image_generation.output")
            if result_output:
                normalized_output = result_output.replace("\\", "/").casefold()
                previous_selector = output_owners.get(normalized_output)
                if previous_selector:
                    raise ShotTimelineError(
                        f"{selector}: result_frame.output collides with {previous_selector} on a case-insensitive filesystem"
                    )
                output_owners[normalized_output] = selector

        entries.append(
            {
                "shot": raw_shot,
                "selector": selector,
                "parent_selector": shot_parent_selector,
                "start_seconds": cursor,
                "duration_seconds": authored_duration,
                "provider_duration_seconds": provider_duration,
            }
        )
        cursor += authored_duration

    if abs(cursor - parent_duration) > _TIMELINE_TOLERANCE:
        raise ShotTimelineError(
            f"{parent_selector}: shot durations must sum to parent cut duration; "
            f"shots={cursor}, parent={parent_duration}"
        )
    if entries and cursor != parent_duration:
        entries[-1]["duration_seconds"] += parent_duration - cursor
    return entries
