from __future__ import annotations

from typing import Any

from toc.providers.elevenlabs import DEFAULT_ELEVENLABS_MODEL_ID, normalize_elevenlabs_model_id


SCRIPT_ELEVENLABS_DEFAULTS = {
    "provider": "elevenlabs",
    "model_id": DEFAULT_ELEVENLABS_MODEL_ID,
    "voice_name": "Jun - Calm, Clear and Husky",
    "voice_id": "JOcmGzB8OFjY8MhjHHEf",
    "prompt_contract_version": "v4_tagged_context_v1",
    "default_stability_profile": "natural",
    "text_policy": "natural_japanese_plus_audio_tags",
}

ALLOWED_STABILITY_PROFILES = {"", "creative", "natural", "robust"}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def normalize_voice_tag(value: Any) -> str:
    text = _as_text(value)
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    return text if "[" not in text and "]" not in text else ""


def normalize_voice_tags(value: Any) -> list[str]:
    tags: list[str] = []
    for raw in _as_list(value):
        tag = normalize_voice_tag(raw)
        if tag:
            tags.append(tag)
    return tags


def normalize_stability_profile(value: Any) -> str:
    text = _as_text(value).lower()
    return text if text in ALLOWED_STABILITY_PROFILES else ""


def materialize_elevenlabs_tts_text(
    *,
    spoken_context: str = "",
    voice_tags: list[str] | None = None,
    spoken_body: str = "",
) -> str:
    tag_text = "".join(f"[{tag}]" for tag in (voice_tags or []) if tag)
    parts = [part for part in (spoken_context.strip(), tag_text, spoken_body.strip()) if part]
    return " ".join(parts).strip()


def resolve_script_cut_elevenlabs_prompt(cut: dict[str, Any]) -> dict[str, Any]:
    prompt = _as_dict(cut.get("elevenlabs_prompt"))
    fallback_tts_text = _as_text(cut.get("tts_text"))
    return {
        "spoken_context": _as_text(prompt.get("spoken_context")),
        "voice_tags": normalize_voice_tags(prompt.get("voice_tags")),
        "spoken_body": _as_text(prompt.get("spoken_body")) or fallback_tts_text,
        "stability_profile": normalize_stability_profile(prompt.get("stability_profile")),
    }


def resolve_script_cut_tts_text(cut: dict[str, Any]) -> str:
    explicit_tts = _as_text(cut.get("tts_text"))
    if explicit_tts:
        return explicit_tts

    prompt = resolve_script_cut_elevenlabs_prompt(cut)
    materialized = materialize_elevenlabs_tts_text(
        spoken_context=str(prompt.get("spoken_context") or ""),
        voice_tags=list(prompt.get("voice_tags") or []),
        spoken_body=str(prompt.get("spoken_body") or ""),
    )
    if materialized:
        return materialized
    return _as_text(cut.get("narration"))


def resolve_script_metadata_elevenlabs(script_data: dict[str, Any]) -> dict[str, str]:
    script_metadata = _as_dict(script_data.get("script_metadata"))
    elevenlabs = _as_dict(script_metadata.get("elevenlabs"))
    merged = dict(SCRIPT_ELEVENLABS_DEFAULTS)
    for key in SCRIPT_ELEVENLABS_DEFAULTS:
        value = _as_text(elevenlabs.get(key))
        if value:
            merged[key] = value
    merged["model_id"] = normalize_elevenlabs_model_id(merged.get("model_id"))
    return merged


def is_b_roll(node: dict[str, Any]) -> bool:
    """Read the authored discriminator, falling back to the existing shot projection."""
    contract = _as_dict(node.get("cut_contract"))
    if "a_roll_or_b_roll" in contract:
        return contract["a_roll_or_b_roll"] == "b_roll"
    image = _as_dict(node.get("image_generation"))
    shot = _as_dict(_as_dict(image.get("api_prompt_payload")).get("shot_design_contract"))
    return shot.get("a_roll_or_b_roll") == "b_roll"


def resolve_manifest_narration(node: dict[str, Any]) -> dict[str, Any] | None:
    """Treat omitted B-roll narration as visual-only, without fabricating approval.

    Explicit provider/text/output/revision data remains authoritative. Invalid
    shapes are not converted to silence. This read-only projection never touches
    subtitles, BGM, effects, or native video audio.
    """
    audio = node.get("audio")
    if audio is not None and not isinstance(audio, dict):
        return None
    narration = _as_dict(audio).get("narration")
    if narration is None and isinstance(node.get("narration"), dict):
        narration = node["narration"]
    if narration is not None and not isinstance(narration, dict):
        return None
    if not is_b_roll(node):
        return narration
    raw = narration or {}
    if any(key not in {"tool", "text", "tts_text", "output"} for key in raw):
        return narration
    if raw.get("tool") not in (None, "", "silent"):
        return narration
    if any(raw.get(key) not in (None, "") for key in ("text", "tts_text", "output")):
        return narration
    return {
        "tool": "silent",
        "text": "",
        "tts_text": "",
        "authoring_status": "silent",
        "silence_contract": {
            "intentional": True,
            "kind": "b_roll",
            "reason": "B-roll narration is optional; use the declared visual duration.",
        },
    }
