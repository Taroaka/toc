from __future__ import annotations

from typing import Any, Iterable


DEFAULT_IMMERSIVE_STORY_SCENE_STEP = 10


def as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def as_opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.lower() in {"null", "none"}:
        return None
    return text


def scene_numeric_id(scene: Any) -> int | None:
    if not isinstance(scene, dict):
        return None
    return as_int(scene.get("scene_id"))


def scene_reference_id(scene: Any) -> str | None:
    if not isinstance(scene, dict):
        return None
    for key in ("reference_id", "character_reference_id"):
        value = as_opt_str(scene.get(key))
        if value:
            return value
    return None


def scene_kind(scene: Any) -> str | None:
    if not isinstance(scene, dict):
        return None
    return as_opt_str(scene.get("kind"))


def is_character_reference_scene(scene: Any) -> bool:
    if not isinstance(scene, dict):
        return False
    if scene_kind(scene) == "character_reference":
        return True
    image_generation = scene.get("image_generation")
    if not isinstance(image_generation, dict):
        return False
    output = as_opt_str(image_generation.get("output")) or ""
    normalized = output.replace("\\", "/")
    return normalized.startswith("assets/characters/") or "/assets/characters/" in normalized


def parse_scene_selectors(scene_ids_csv: str | None) -> set[str] | None:
    if not scene_ids_csv:
        return None
    selectors = {token.strip() for token in str(scene_ids_csv).split(",") if token.strip()}
    return selectors or None


def scene_selector_tokens(
    *,
    operational_scene_id: int | None = None,
    manifest_scene_id: int | None = None,
    reference_id: str | None = None,
) -> set[str]:
    tokens: set[str] = set()
    for value in (operational_scene_id, manifest_scene_id):
        if value is not None:
            tokens.add(str(int(value)))
    ref = as_opt_str(reference_id)
    if ref:
        tokens.add(ref)
    return tokens


def manifest_scene_selector_tokens(scene: Any) -> set[str]:
    return scene_selector_tokens(
        operational_scene_id=scene_numeric_id(scene),
        manifest_scene_id=scene_numeric_id(scene),
        reference_id=scene_reference_id(scene),
    )


def selector_matches(tokens: Iterable[str], selectors: set[str] | None) -> bool:
    if selectors is None:
        return True
    return any(token in selectors for token in tokens)


def story_scene_ids(raw_scenes: Iterable[Any]) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for scene in raw_scenes:
        if is_character_reference_scene(scene):
            continue
        scene_id = scene_numeric_id(scene)
        if scene_id is None or scene_id < 0:
            continue
        if scene_id in seen:
            continue
        seen.add(scene_id)
        ids.append(int(scene_id))
    return sorted(ids)


def default_story_scene_start(raw_scenes: Iterable[Any], *, fallback: int = DEFAULT_IMMERSIVE_STORY_SCENE_STEP) -> int:
    ids = story_scene_ids(raw_scenes)
    if not ids:
        return int(fallback)
    return min(ids)
