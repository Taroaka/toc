from __future__ import annotations

import re
from typing import Any, Iterable


DEFAULT_IMMERSIVE_STORY_SCENE_STEP = 10
_DOTTED_ID_RE = re.compile(r"^\d+(?:\.\d+)*$")


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


def normalize_dotted_id(value: Any) -> str | None:
    text = as_opt_str(value)
    if not text:
        return None
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if _DOTTED_ID_RE.fullmatch(text):
        try:
            return ".".join(str(int(part)) for part in text.split("."))
        except Exception:
            return None
    return None


def dotted_id_parts(value: Any) -> tuple[int, ...] | None:
    normalized = normalize_dotted_id(value)
    if not normalized:
        return None
    try:
        return tuple(int(part) for part in normalized.split("."))
    except Exception:
        return None


def dotted_id_sort_key(value: Any) -> tuple[int, ...]:
    parts = dotted_id_parts(value)
    if parts is None:
        return (10**9,)
    return parts


def dotted_id_slug(value: Any) -> str:
    normalized = normalize_dotted_id(value)
    if not normalized:
        raw = as_opt_str(value) or "unknown"
        return raw.replace(".", "_")
    return normalized.replace(".", "_")


def make_scene_cut_selector(scene_id: Any, cut_id: Any | None = None) -> str:
    scene = normalize_dotted_id(scene_id) or "unknown"
    if cut_id is None:
        return f"scene{scene}"
    cut = normalize_dotted_id(cut_id) or "unknown"
    return f"scene{scene}_cut{cut}"


def selector_aliases(scene_id: Any, cut_id: Any | None = None) -> set[str]:
    aliases = {make_scene_cut_selector(scene_id, cut_id)}
    scene_int = as_int(scene_id)
    cut_int = as_int(cut_id) if cut_id is not None else None
    if scene_int is not None:
        if cut_id is None:
            aliases.add(f"scene{scene_int:02d}")
        elif cut_int is not None:
            aliases.add(f"scene{scene_int:02d}_cut{cut_int:02d}")
    return aliases


def scene_numeric_id(scene: Any) -> int | None:
    if not isinstance(scene, dict):
        return None
    return as_int(scene.get("scene_id"))


def scene_dotted_id(scene: Any) -> str | None:
    if not isinstance(scene, dict):
        return None
    return normalize_dotted_id(scene.get("scene_id"))


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
    operational_scene_id: Any | None = None,
    manifest_scene_id: Any | None = None,
    reference_id: str | None = None,
) -> set[str]:
    tokens: set[str] = set()
    for value in (operational_scene_id, manifest_scene_id):
        raw = as_opt_str(value)
        if raw:
            tokens.add(raw)
        normalized = normalize_dotted_id(value)
        if normalized is not None:
            tokens.add(normalized)
            if as_int(value) is not None:
                tokens.add(str(int(value)))
    ref = as_opt_str(reference_id)
    if ref:
        tokens.add(ref)
    return tokens


def manifest_scene_selector_tokens(scene: Any) -> set[str]:
    return scene_selector_tokens(
        operational_scene_id=scene_dotted_id(scene) or scene_numeric_id(scene),
        manifest_scene_id=scene_dotted_id(scene) or scene_numeric_id(scene),
        reference_id=scene_reference_id(scene),
    )


def selector_matches(tokens: Iterable[str], selectors: set[str] | None) -> bool:
    if selectors is None:
        return True
    return any(token in selectors for token in tokens)


def story_scene_ids(raw_scenes: Iterable[Any]) -> list[int | str]:
    ids: list[int | str] = []
    seen: set[str] = set()
    for scene in raw_scenes:
        if is_character_reference_scene(scene):
            continue
        scene_id = scene_dotted_id(scene)
        if scene_id is None:
            numeric = scene_numeric_id(scene)
            if numeric is None or numeric < 0:
                continue
            scene_id = str(numeric)
        if scene_id in seen:
            continue
        seen.add(scene_id)
        ids.append(int(scene_id) if scene_id.isdigit() else scene_id)
    return sorted(ids, key=dotted_id_sort_key)


def default_story_scene_start(raw_scenes: Iterable[Any], *, fallback: int = DEFAULT_IMMERSIVE_STORY_SCENE_STEP) -> int | str:
    ids = story_scene_ids(raw_scenes)
    if not ids:
        return int(fallback)
    return ids[0]
