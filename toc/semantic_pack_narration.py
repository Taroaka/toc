from __future__ import annotations

import re
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


QUALITY_REVIEW_CANDIDATES = (
    Path("narration_text_review.md"),
    Path("narration_review.md"),
    Path("logs/review/narration_text_review.md"),
    Path("logs/review/narration_text_quality.md"),
)


def collect_entries(stage: str, run_dir: Path, manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    if stage != "narration":
        raise ValueError(f"semantic_pack_narration only supports stage='narration', got {stage!r}")
    manifest_data = manifest if manifest is not None else load_manifest(run_dir / "video_manifest.md")
    entries: list[dict[str, Any]] = []
    for scene in _iter_dicts(manifest_data.get("scenes")):
        scene_id = scene.get("scene_id")
        cuts = list(_iter_dicts(scene.get("cuts")))
        if cuts:
            for index, cut in enumerate(cuts):
                entry = _entry_from_node(
                    run_dir=run_dir,
                    scene=scene,
                    cut=cut,
                    scene_level=False,
                    previous_cut=cuts[index - 1] if index > 0 else None,
                    next_cut=cuts[index + 1] if index + 1 < len(cuts) else None,
                )
                if entry is not None:
                    entries.append(entry)
            continue
        entry = _entry_from_node(
            run_dir=run_dir,
            scene=scene,
            cut=None,
            scene_level=True,
            previous_cut=None,
            next_cut=None,
        )
        if entry is not None:
            entries.append(entry)
    return entries


def load_manifest(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required to collect narration semantic review entries.")
    text = path.read_text(encoding="utf-8")
    block = extract_yaml_block(text)
    data = yaml.safe_load(block) or {}
    return data if isinstance(data, dict) else {}


def extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml\s*\n(.*?)\n```", text, re.S)
    if match:
        return match.group(1)
    return text


def _entry_from_node(
    *,
    run_dir: Path,
    scene: dict[str, Any],
    cut: dict[str, Any] | None,
    scene_level: bool,
    previous_cut: dict[str, Any] | None,
    next_cut: dict[str, Any] | None,
) -> dict[str, Any] | None:
    node = scene if scene_level else (cut or {})
    narration = _narration_from_node(node)
    if not narration:
        return None

    scene_id = scene.get("scene_id")
    cut_id = None if scene_level else node.get("cut_id")
    selector = _selector(scene_id=scene_id, cut_id=cut_id, explicit=node.get("selector"))
    if not selector:
        return None

    output = _as_str(narration.get("output"))
    text_quality_review = _quality_review_for_selector(run_dir, selector)
    semantic_contract = _semantic_contract(narration, node)
    cut_contract = _dict_or_empty(node.get("cut_contract"))
    source_event_contract = _dict_or_empty(cut_contract.get("source_event_contract"))
    event_context_for_cut = _dict_or_empty(cut_contract.get("event_context_for_cut"))
    missing_required_contract_fields = _missing_required_contract_fields(semantic_contract)
    tool = _as_str(narration.get("tool")).lower()
    silence_contract = _dict_or_empty(narration.get("silence_contract"))
    silence_contract_missing = tool == "silent" and _silence_contract_missing(silence_contract)
    output_check = _audio_output_check(run_dir=run_dir, output=output, node=node, narration=narration)
    design_context = {
        "scene_title": _as_str(scene.get("title") or scene.get("scene_title")),
        "scene_role": _as_str(scene.get("scene_role") or scene.get("story_role")),
        "cut_role": _as_str(node.get("cut_role")),
        "duration_seconds": node.get("duration_seconds") or scene.get("duration_seconds"),
        "scene_contract": _dict_or_empty(scene.get("scene_contract") or scene.get("contract")),
        "visual_beat": _visual_beat(node),
        "previous_cut_summary": _cut_summary(previous_cut),
        "next_cut_summary": _cut_summary(next_cut),
    }
    semantic_review_inputs = {
        "selector": selector,
        "semantic_contract": semantic_contract,
        "semantic_contract_missing": not bool(semantic_contract),
        "contract_required_fields_missing": missing_required_contract_fields,
        "scene_contract": design_context["scene_contract"],
        "cut_role": design_context["cut_role"],
        "visual_beat": design_context["visual_beat"],
        "previous_cut_summary": design_context["previous_cut_summary"],
        "next_cut_summary": design_context["next_cut_summary"],
        "narration_text_summary": _summary(narration.get("text")),
        "tts_text_summary": _summary(narration.get("tts_text")),
        "silent_narration": tool == "silent",
        "silence_contract_missing": silence_contract_missing,
        "silence_contract_reason": _silence_contract_reason(silence_contract),
        "too_visual_redundant_check": _too_visual_redundant_check(narration=narration, design_context=design_context),
        "audio_output_check": output_check,
        "source_event_contract": source_event_contract,
        "event_context_for_cut": event_context_for_cut,
    }
    entry = {
        "stage": "narration",
        "selector": selector,
        "scene_id": scene_id,
        "cut_id": cut_id,
        "source": "video_manifest.md:scenes[].audio.narration"
        if scene_level
        else "video_manifest.md:scenes[].cuts[].audio.narration",
        "context": design_context,
        "cut_role": design_context["cut_role"],
        "scene_contract": design_context["scene_contract"],
        "visual_beat": design_context["visual_beat"],
        "previous_cut_summary": design_context["previous_cut_summary"],
        "next_cut_summary": design_context["next_cut_summary"],
        "narration": {
            "tool": _as_str(narration.get("tool")),
            "text": _as_str(narration.get("text")),
            "text_summary": _summary(narration.get("text")),
            "tts_text": _as_str(narration.get("tts_text")),
            "tts_text_summary": _summary(narration.get("tts_text")),
            "output": output,
            "output_exists": output_check["exists"],
            "normalize_to_scene_duration": narration.get("normalize_to_scene_duration"),
            "silence_contract": silence_contract,
        },
        "semantic_contract": semantic_contract,
        "source_event_contract": source_event_contract,
        "event_context_for_cut": event_context_for_cut,
        "semantic_contract_missing": not bool(semantic_contract),
        "contract_required_fields_missing": missing_required_contract_fields,
        "semantic_review_inputs": semantic_review_inputs,
        "text_quality_review": text_quality_review,
        "quality_review": text_quality_review,
        "silence_contract_missing": silence_contract_missing,
        "silence_contract_reason": _silence_contract_reason(silence_contract),
        "too_visual_redundant_check": semantic_review_inputs["too_visual_redundant_check"],
        "audio_output_check": output_check,
        "audio_output_refs": [output] if output else [],
    }
    return entry


def _narration_from_node(node: dict[str, Any]) -> dict[str, Any]:
    audio = node.get("audio")
    if isinstance(audio, dict) and isinstance(audio.get("narration"), dict):
        return audio["narration"]
    narration = node.get("narration")
    return narration if isinstance(narration, dict) else {}


def _semantic_contract(narration: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    contract = narration.get("contract")
    if isinstance(contract, dict):
        return contract
    audio = node.get("audio")
    if isinstance(audio, dict) and isinstance(audio.get("narration_contract"), dict):
        return audio["narration_contract"]
    fallback = node.get("narration_contract")
    if isinstance(fallback, dict):
        return fallback
    cut_contract = node.get("cut_contract")
    if isinstance(cut_contract, dict) and isinstance(cut_contract.get("narration_contract"), dict):
        return cut_contract["narration_contract"]
    return {}


def _missing_required_contract_fields(contract: dict[str, Any]) -> list[str]:
    required = ("target_function", "must_cover", "must_avoid", "done_when")
    missing: list[str] = []
    for key in required:
        value = contract.get(key)
        if isinstance(value, str) and value.strip():
            continue
        if isinstance(value, list) and any(_as_str(item) for item in value):
            continue
        missing.append(key)
    return missing


def _visual_beat(node: dict[str, Any]) -> str:
    for key in ("visual_beat", "target_beat", "beat", "description", "action", "shot_description"):
        value = _as_str(node.get(key))
        if value:
            return value
    image_generation = node.get("image_generation")
    if isinstance(image_generation, dict):
        return _summary(image_generation.get("prompt"))
    return ""


def _cut_summary(cut: dict[str, Any] | None) -> str:
    if not cut:
        return ""
    for key in ("cut_summary", "summary", "visual_beat", "target_beat", "beat", "description", "action"):
        value = _as_str(cut.get(key))
        if value:
            return _summary(value)
    narration = _narration_from_node(cut)
    if narration:
        return _summary(narration.get("text") or narration.get("tts_text"))
    return ""


def _silence_contract_missing(silence_contract: dict[str, Any]) -> bool:
    if not silence_contract:
        return True
    return not (
        silence_contract.get("intentional") is True
        and silence_contract.get("confirmed_by_human") is True
        and _as_str(silence_contract.get("kind"))
        and _as_str(silence_contract.get("reason"))
    )


def _silence_contract_reason(silence_contract: dict[str, Any]) -> str:
    reason = _as_str(silence_contract.get("reason"))
    kind = _as_str(silence_contract.get("kind"))
    if reason and kind:
        return f"{kind}: {reason}"
    return reason or kind


def _too_visual_redundant_check(*, narration: dict[str, Any], design_context: dict[str, Any]) -> dict[str, Any]:
    narration_text = _as_str(narration.get("tts_text") or narration.get("text"))
    visual_beat = _as_str(design_context.get("visual_beat"))
    return {
        "narration_text_summary": _summary(narration_text),
        "visual_beat_summary": _summary(visual_beat),
        "review_question": "Does the narration merely restate visible action instead of adding causality, emotion, time, or story meaning?",
        "text_exactly_matches_visual_beat": bool(narration_text and visual_beat and narration_text == visual_beat),
    }


def _audio_output_check(
    *,
    run_dir: Path,
    output: str,
    node: dict[str, Any],
    narration: dict[str, Any],
) -> dict[str, Any]:
    path = run_dir / output if output else None
    exists = bool(path and path.exists())
    size_bytes = path.stat().st_size if path and exists else None
    return {
        "path": output,
        "exists": exists,
        "size_bytes": size_bytes,
        "empty_file": bool(exists and size_bytes == 0),
        "expected_duration_seconds": node.get("duration_seconds"),
        "declared_duration_seconds": narration.get("duration_seconds") or narration.get("audio_duration_seconds"),
        "measured_duration_seconds": None,
        "duration_source": "not_measured",
    }


def _quality_review_for_selector(run_dir: Path, selector: str) -> dict[str, Any]:
    artifacts = [path.as_posix() for path in QUALITY_REVIEW_CANDIDATES if (run_dir / path).exists()]
    review: dict[str, Any] = {
        "artifacts": artifacts,
        "status": "",
        "agent_review_ok": None,
        "human_review_ok": None,
        "reason_keys": [],
        "reason_messages": [],
    }
    for rel in artifacts:
        text = (run_dir / rel).read_text(encoding="utf-8")
        block = _markdown_section(text, selector)
        if not block:
            continue
        review["artifact"] = rel
        status = _backtick_value(block, "review") or _backtick_value(block, "status")
        if status:
            review["status"] = status.lower()
        agent_ok = _bool_value(block, "agent_review_ok")
        if agent_ok is not None:
            review["agent_review_ok"] = agent_ok
        human_ok = _bool_value(block, "human_review_ok")
        if human_ok is not None:
            review["human_review_ok"] = human_ok
        keys = _comma_values(_backtick_value(block, "agent_review_reason_keys"))
        if keys:
            review["reason_keys"] = keys
        messages = _bullet_values_after_label(block, "agent_review_reason_messages")
        if messages:
            review["reason_messages"] = messages
        break
    return review


def _markdown_section(text: str, selector: str) -> str:
    pattern = re.compile(rf"^##\s+{re.escape(selector)}\s*$", re.M)
    match = pattern.search(text)
    if not match:
        return ""
    next_match = re.search(r"^##\s+", text[match.end() :], re.M)
    end = match.end() + next_match.start() if next_match else len(text)
    return text[match.start() : end]


def _backtick_value(text: str, key: str) -> str:
    match = re.search(rf"^-\s*{re.escape(key)}:\s*`([^`]*)`", text, re.M)
    return match.group(1).strip() if match else ""


def _bool_value(text: str, key: str) -> bool | None:
    value = _backtick_value(text, key).lower()
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _bullet_values_after_label(text: str, key: str) -> list[str]:
    match = re.search(rf"^-\s*{re.escape(key)}:\s*\n((?:\s+-\s+.*\n?)*)", text, re.M)
    if not match:
        return []
    return [line.strip()[2:].strip(" `") for line in match.group(1).splitlines() if line.strip().startswith("- ")]


def _selector(*, scene_id: Any, cut_id: Any, explicit: Any) -> str:
    explicit_s = _as_str(explicit)
    if explicit_s:
        return explicit_s
    scene_digits = re.sub(r"\D+", "", str(scene_id or ""))
    if not scene_digits:
        return ""
    if cut_id in {None, ""}:
        return f"scene{int(scene_digits):02d}"
    cut_token = str(cut_id).split("-")[-1]
    cut_digits = re.sub(r"\D+", "", cut_token)
    if not cut_digits:
        return ""
    return f"scene{int(scene_digits):02d}_cut{int(cut_digits):02d}"


def _summary(value: Any, *, limit: int = 120) -> str:
    text = re.sub(r"\s+", " ", _as_str(value))
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _comma_values(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _iter_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_str(value: Any) -> str:
    return str(value).strip() if value is not None else ""
