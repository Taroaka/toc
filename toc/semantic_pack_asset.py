"""Asset-stage collectors for semantic review pack generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from toc.harness import load_structured_document


ASSET_PLAN_STAGE = "asset_plan"
ASSET_OUTPUT_STAGE = "asset_output"
ASSET_STAGES = {ASSET_PLAN_STAGE, ASSET_OUTPUT_STAGE}
ASSET_CATEGORY_USAGE_KEYS = {
    "character_ids": "characters",
    "object_ids": "objects",
    "location_ids": "locations",
    "setpiece_ids": "setpieces",
    "asset_ids": "assets",
    "references": "references",
}
ASSET_REVIEW_RUBRICS = {
    "characters": [
        "identity remains consistent across all referenced selectors",
        "age/body/clothing details match the story role and visual_spec",
        "full-body reference requirements are present when required",
        "forbidden props or later-story objects are not accidentally attached",
    ],
    "character": [
        "identity remains consistent across all referenced selectors",
        "age/body/clothing details match the story role and visual_spec",
        "full-body reference requirements are present when required",
        "forbidden props or later-story objects are not accidentally attached",
    ],
    "objects": [
        "object material, scale, and uniqueness match the story-specific function",
        "object appears only in selectors allowed by the semantic contract",
        "object is not used as a location, character, or ambient decoration",
    ],
    "object": [
        "object material, scale, and uniqueness match the story-specific function",
        "object appears only in selectors allowed by the semantic contract",
        "object is not used as a location, character, or ambient decoration",
    ],
    "locations": [
        "space, era, geography, and mood match the scene context",
        "location is used as an environment reference rather than a character/object",
        "recurring spatial details remain stable across selectors",
    ],
    "location": [
        "space, era, geography, and mood match the scene context",
        "location is used as an environment reference rather than a character/object",
        "recurring spatial details remain stable across selectors",
    ],
    "setpieces": [
        "setpiece supports the intended scene function and visual reveal",
        "scale and placement remain plausible in the referenced selectors",
        "setpiece is not substituted for a generic location or object",
    ],
    "setpiece": [
        "setpiece supports the intended scene function and visual reveal",
        "scale and placement remain plausible in the referenced selectors",
        "setpiece is not substituted for a generic location or object",
    ],
    "reusable_stills": [
        "still image remains reusable without contradicting selector-specific action",
        "still does not introduce story elements before their intended reveal",
    ],
}


def collect_entries(stage: str, run_dir: Path, manifest: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Collect asset entries for a semantic review dispatcher.

    The collector is intentionally read-only. It normalizes the asset inventory,
    asset plan, generation requests, generation manifests, generated output paths,
    and video-manifest usage into stable dictionaries that a generic semantic
    review pack builder can render.
    """

    stage = stage.strip()
    if stage not in ASSET_STAGES:
        raise ValueError(f"unsupported asset semantic stage: {stage}")

    inventory_text, inventory_data = _load_optional_structured(run_dir / "asset_inventory.md")
    _plan_text, plan_data = _load_optional_structured(run_dir / "asset_plan.md")
    inventory_root = _inventory_root(inventory_data)
    inventory_by_id = _inventory_items_by_id(inventory_root)
    plan_entries = _asset_entries(plan_data)
    if not plan_entries and stage == ASSET_PLAN_STAGE:
        return [_entry_from_inventory(item, run_dir=run_dir, inventory_text=inventory_text) for item in inventory_by_id.values()]

    requests_by_id = _request_sections_by_asset_id(_read_optional(run_dir / "asset_generation_requests.md"))
    manifest_items_by_id = _manifest_items_by_id(run_dir, extra_manifest=manifest)
    video_manifest = manifest if manifest is not None else _load_video_manifest(run_dir)
    usage_events = _usage_events_by_asset_id(video_manifest)
    alias_index = _alias_index(plan_entries, inventory_by_id)
    usage_by_canonical_id = _usage_by_canonical_id(usage_events, alias_index)
    used_canonical_ids = set(usage_by_canonical_id)
    planned_canonical_ids = {_canonical_asset_id(_entry_asset_id(entry)) for entry in plan_entries if _entry_asset_id(entry)}
    contact_sheets = _contact_sheet_refs(run_dir)

    entries: list[dict[str, Any]] = []
    for plan_entry in plan_entries:
        asset_id = _entry_asset_id(plan_entry)
        inventory_item = inventory_by_id.get(asset_id, {})
        canonical_asset_id = _canonical_asset_id(asset_id)
        usage_events_for_entry = usage_by_canonical_id.get(canonical_asset_id, [])
        request = requests_by_id.get(asset_id, {})
        manifest_item = manifest_items_by_id.get(asset_id, {})
        entry = _entry_from_plan(
            plan_entry,
            stage=stage,
            inventory_item=inventory_item,
            run_dir=run_dir,
            usage_events=usage_events_for_entry,
        )
        if stage == ASSET_OUTPUT_STAGE:
            outputs = _output_refs(run_dir, plan_entry=plan_entry, request=request, manifest_item=manifest_item)
            entry.update(
                {
                    "request_metadata": request,
                    "generation_manifest_item": manifest_item,
                    "generated_outputs": outputs,
                    "contact_sheets": contact_sheets,
                    "source_paths": _source_paths(
                        run_dir,
                        [
                            "asset_inventory.md",
                            "asset_plan.md",
                            "asset_generation_requests.md",
                            "asset_generation_manifest.md",
                            "location_asset_generation_manifest.md",
                            "video_manifest.md",
                        ],
                    ),
                }
            )
        entries.append(entry)
    for canonical_asset_id in sorted(used_canonical_ids - planned_canonical_ids):
        events = usage_by_canonical_id[canonical_asset_id]
        raw_ids = sorted({_clean(event.get("raw_asset_id")) for event in events if _clean(event.get("raw_asset_id"))})
        entries.append(
            {
                "stage": stage,
                "asset_id": raw_ids[0] if raw_ids else canonical_asset_id,
                "canonical_asset_id": canonical_asset_id,
                "aliases": raw_ids or [canonical_asset_id],
                "category": "",
                "asset_type": "",
                "source_paths": _source_paths(run_dir, ["video_manifest.md"]),
                "source_script_selectors": [],
                "story_purpose": "",
                "semantic_contract": _normalize_semantic_contract({}, {}),
                "review_rubric": _review_rubric_for_category(""),
                "used_by_selectors": _selectors_from_usage_events(events),
                "usage_events": events,
                "planned_but_unused": False,
                "used_but_unplanned": True,
                "wrong_category_usage": [],
                "suggested_fix_targets": ["asset_inventory.md", "asset_plan.md", "video_manifest.md"],
            }
        )
    return entries


def _load_optional_structured(path: Path) -> tuple[str, dict[str, Any]]:
    if not path.exists():
        return "", {}
    return load_structured_document(path)


def _read_optional(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _inventory_root(data: dict[str, Any]) -> dict[str, Any]:
    root = data.get("asset_inventory")
    if isinstance(root, dict):
        return root
    return data if isinstance(data, dict) else {}


def _inventory_items_by_id(root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for item in _as_list(root.get("items")):
        if not isinstance(item, dict):
            continue
        item_id = _clean(item.get("item_id") or item.get("asset_id"))
        if item_id:
            out[item_id] = item
    return out


def _asset_entries(asset_plan: dict[str, Any]) -> list[dict[str, Any]]:
    assets = asset_plan.get("assets")
    if isinstance(assets, list):
        return [item for item in assets if isinstance(item, dict)]
    if not isinstance(assets, dict):
        return []

    entries: list[dict[str, Any]] = []
    for category in ("characters", "objects", "locations", "setpieces", "reusable_stills"):
        for item in _as_list(assets.get(category)):
            if isinstance(item, dict):
                copied = dict(item)
                copied.setdefault("_category", category)
                entries.append(copied)
    return entries


def _entry_asset_id(entry: dict[str, Any]) -> str:
    return _clean(entry.get("asset_id") or entry.get("item_id") or entry.get("selector"))


def _entry_category(entry: dict[str, Any], inventory_item: Optional[dict[str, Any]] = None) -> str:
    inventory_item = inventory_item or {}
    return _clean(entry.get("_category") or entry.get("category") or inventory_item.get("category") or entry.get("asset_type"))


def _entry_generation_plan(entry: dict[str, Any]) -> dict[str, Any]:
    plan = entry.get("generation_plan")
    return plan if isinstance(plan, dict) else {}


def _entry_review(entry: dict[str, Any]) -> dict[str, Any]:
    review = entry.get("review")
    return review if isinstance(review, dict) else {}


def _source_paths(run_dir: Path, names: list[str]) -> list[str]:
    return [name for name in names if (run_dir / name).exists()]


def _semantic_contract(entry: dict[str, Any], inventory_item: dict[str, Any]) -> dict[str, Any]:
    explicit = entry.get("semantic_contract")
    if isinstance(explicit, dict):
        return _normalize_semantic_contract(explicit, entry)
    contract: dict[str, Any] = {}
    for key in ("story_purpose", "visual_spec", "source_script_selectors", "asset_type"):
        if key in entry:
            contract[key] = entry[key]
    if inventory_item:
        contract["inventory"] = {
            key: inventory_item.get(key)
            for key in ("category", "story_purpose", "reusable_reason", "recommended_asset_type")
            if key in inventory_item
        }
    review = _entry_review(entry)
    if review:
        contract["review"] = review
    return _normalize_semantic_contract(contract, entry)


def _normalize_semantic_contract(contract: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(contract)
    for key in ("must_appear_in_selectors", "must_not_appear_in_selectors", "allowed_contexts"):
        value = normalized.get(key)
        if value is None:
            value = entry.get(key)
        normalized[key] = _normalized_string_list(value)
    return normalized


def _normalized_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        candidates = [value]
    elif isinstance(value, (list, tuple, set)):
        candidates = list(value)
    else:
        candidates = []
    out: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        text = _clean(item)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _entry_from_plan(
    entry: dict[str, Any],
    *,
    stage: str,
    inventory_item: dict[str, Any],
    run_dir: Path,
    usage_events: list[dict[str, str]],
) -> dict[str, Any]:
    generation_plan = _entry_generation_plan(entry)
    asset_id = _entry_asset_id(entry)
    category = _entry_category(entry, inventory_item)
    canonical_asset_id = _canonical_asset_id(asset_id)
    used_by_selectors = _selectors_from_usage_events(usage_events)
    semantic_contract = _semantic_contract(entry, inventory_item)
    wrong_category_usage = _wrong_category_usage(category, usage_events)
    return {
        "stage": stage,
        "asset_id": asset_id,
        "canonical_asset_id": canonical_asset_id,
        "aliases": _aliases_for_entry(entry, inventory_item),
        "category": category,
        "asset_type": _clean(entry.get("asset_type") or inventory_item.get("recommended_asset_type")),
        "source_paths": _source_paths(run_dir, ["asset_inventory.md", "asset_plan.md", "video_manifest.md"]),
        "source_script_selectors": [_clean(item) for item in _as_list(entry.get("source_script_selectors")) if _clean(item)],
        "story_purpose": _clean(entry.get("story_purpose") or inventory_item.get("story_purpose")),
        "semantic_contract": semantic_contract,
        "review_rubric": _review_rubric_for_category(category),
        "visual_spec": entry.get("visual_spec") if isinstance(entry.get("visual_spec"), dict) else {},
        "generation_plan": {
            key: generation_plan.get(key)
            for key in (
                "output",
                "output_path",
                "output_dir",
                "required_views",
                "reference_inputs",
                "derived_from_asset_id",
                "execution_lane",
                "bootstrap_allowed",
            )
            if key in generation_plan
        },
        "review_status": _clean(_entry_review(entry).get("status")),
        "used_by_selectors": used_by_selectors,
        "usage_events": usage_events,
        "planned_but_unused": not used_by_selectors,
        "used_but_unplanned": False,
        "wrong_category_usage": wrong_category_usage,
        "suggested_fix_targets": _suggested_fix_targets(
            semantic_contract=semantic_contract,
            planned_but_unused=not used_by_selectors,
            wrong_category_usage=wrong_category_usage,
        ),
    }


def _entry_from_inventory(entry: dict[str, Any], *, run_dir: Path, inventory_text: str) -> dict[str, Any]:
    asset_id = _entry_asset_id(entry)
    category = _entry_category(entry)
    semantic_contract = _normalize_semantic_contract(
        {
            "story_purpose": entry.get("story_purpose"),
            "reusable_reason": entry.get("reusable_reason"),
            "recommended_asset_type": entry.get("recommended_asset_type"),
        },
        entry,
    )
    return {
        "stage": ASSET_PLAN_STAGE,
        "asset_id": asset_id,
        "canonical_asset_id": _canonical_asset_id(asset_id),
        "aliases": _aliases_for_entry(entry, {}),
        "category": category,
        "asset_type": _clean(entry.get("recommended_asset_type")),
        "source_paths": _source_paths(run_dir, ["asset_inventory.md"]),
        "source_script_selectors": [_clean(item) for item in _as_list(entry.get("source_script_selectors")) if _clean(item)],
        "story_purpose": _clean(entry.get("story_purpose")),
        "semantic_contract": semantic_contract,
        "review_rubric": _review_rubric_for_category(category),
        "used_by_selectors": [],
        "usage_events": [],
        "planned_but_unused": True,
        "used_but_unplanned": False,
        "wrong_category_usage": [],
        "suggested_fix_targets": ["asset_plan.md"],
        "inventory_only": True,
        "inventory_has_content": bool(inventory_text.strip()),
    }


def _request_sections_by_asset_id(text: str) -> dict[str, dict[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading or current_lines:
                sections.append((current_heading, current_lines))
            current_heading = line.removeprefix("## ").strip()
            current_lines = []
            continue
        current_lines.append(line)
    if current_heading or current_lines:
        sections.append((current_heading, current_lines))

    out: dict[str, dict[str, str]] = {}
    field_pattern = re.compile(r"^\s*-\s+([A-Za-z0-9_.]+):\s*(.*?)\s*$")
    for heading, lines in sections:
        fields: dict[str, str] = {}
        for line in lines:
            match = field_pattern.match(line)
            if not match:
                continue
            value = match.group(2).strip()
            if value.startswith("`") and value.endswith("`") and len(value) >= 2:
                value = value[1:-1]
            fields[match.group(1)] = value
        asset_id = _clean(fields.get("asset_id") or heading).strip("` ")
        if asset_id:
            out[asset_id] = fields
    return out


def _manifest_items_by_id(run_dir: Path, *, extra_manifest: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in (run_dir / "asset_generation_manifest.md", run_dir / "location_asset_generation_manifest.md"):
        if not path.exists():
            continue
        _text, data = load_structured_document(path)
        for item in _asset_manifest_items(data):
            asset_id = _clean(item.get("asset_id") or item.get("selector"))
            if asset_id:
                out[asset_id] = item
    if extra_manifest:
        for item in _asset_manifest_items(extra_manifest):
            asset_id = _clean(item.get("asset_id") or item.get("selector"))
            if asset_id:
                out.setdefault(asset_id, item)
    return out


def _asset_manifest_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data.get("asset_generation_manifest"), dict):
        return [item for item in _as_list(data["asset_generation_manifest"].get("items")) if isinstance(item, dict)]
    if isinstance(data.get("assets"), list):
        return [item for item in data["assets"] if isinstance(item, dict)]
    if isinstance(data.get("items"), list):
        return [item for item in data["items"] if isinstance(item, dict)]
    return []


def _load_video_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "video_manifest.md"
    if not path.exists():
        return {}
    _text, data = load_structured_document(path)
    return data


def _usage_events_by_asset_id(manifest: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    usage: dict[str, list[dict[str, str]]] = {}
    for node in _iter_manifest_nodes(manifest):
        selector = _clean(node.get("selector") or node.get("id") or node.get("cut_id") or node.get("scene_id"))
        image_generation = node.get("image_generation") if isinstance(node.get("image_generation"), dict) else {}
        for key in ("asset_ids", "character_ids", "object_ids", "location_ids", "setpiece_ids"):
            for raw in _as_list(image_generation.get(key)):
                _append_usage_events(usage, raw, selector=selector, usage_key=key)
        for raw in _as_list(node.get("asset_ids")):
            _append_usage_events(usage, raw, selector=selector, usage_key="asset_ids")
        refs = image_generation.get("references")
        if isinstance(refs, list):
            for raw in refs:
                _append_usage_events(usage, raw, selector=selector, usage_key="references")
        elif isinstance(refs, dict):
            for raw in refs.keys():
                _append_usage_events(usage, raw, selector=selector, usage_key="references")
            for raw in refs.values():
                _append_usage_events(usage, raw, selector=selector, usage_key="references")
    return usage


def _append_usage_events(usage: dict[str, list[dict[str, str]]], raw: Any, *, selector: str, usage_key: str) -> None:
    for asset_id in _extract_asset_ids(raw):
        if not asset_id:
            continue
        event = {
            "selector": selector or "(unknown selector)",
            "usage_key": usage_key,
            "usage_category": ASSET_CATEGORY_USAGE_KEYS.get(usage_key, usage_key),
            "raw_asset_id": asset_id,
        }
        usage.setdefault(asset_id, []).append(event)


def _usage_by_canonical_id(
    usage_events: dict[str, list[dict[str, str]]],
    alias_index: dict[str, str],
) -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    seen: set[tuple[str, str, str, str]] = set()
    for raw_id, events in usage_events.items():
        canonical = alias_index.get(_canonical_asset_id(raw_id), _canonical_asset_id(raw_id))
        for event in events:
            key = (canonical, event.get("selector", ""), event.get("usage_key", ""), event.get("raw_asset_id", ""))
            if key in seen:
                continue
            seen.add(key)
            out.setdefault(canonical, []).append(event)
    return {canonical: sorted(events, key=lambda item: (item["selector"], item["usage_key"], item["raw_asset_id"])) for canonical, events in out.items()}


def _selectors_from_usage_events(events: list[dict[str, str]]) -> list[str]:
    return sorted({_clean(event.get("selector")) for event in events if _clean(event.get("selector"))})


def _alias_index(plan_entries: list[dict[str, Any]], inventory_by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for entry in plan_entries:
        asset_id = _entry_asset_id(entry)
        canonical = _canonical_asset_id(asset_id)
        if not canonical:
            continue
        inventory_item = inventory_by_id.get(asset_id, {})
        for alias in _aliases_for_entry(entry, inventory_item):
            alias_canonical = _canonical_asset_id(alias)
            if alias_canonical:
                out[alias_canonical] = canonical
    return out


def _canonical_asset_id(value: Any) -> str:
    text = _clean(value)
    if "/" in text:
        text = Path(text).stem
    text = text.lower()
    text = re.sub(r"[^\w]+", "_", text)
    return text.strip("_")


def _aliases_for_entry(entry: dict[str, Any], inventory_item: dict[str, Any]) -> list[str]:
    generation_plan = _entry_generation_plan(entry)
    candidates: list[Any] = [
        entry.get("asset_id"),
        entry.get("item_id"),
        entry.get("selector"),
        entry.get("display_name"),
        entry.get("name"),
        inventory_item.get("item_id"),
        inventory_item.get("asset_id"),
        inventory_item.get("display_name"),
        inventory_item.get("name"),
        generation_plan.get("output"),
        generation_plan.get("output_path"),
    ]
    candidates.extend(_as_list(entry.get("aliases")))
    candidates.extend(_as_list(inventory_item.get("aliases")))
    for raw in _as_list(entry.get("existing_outputs")):
        candidates.append(raw)

    aliases: list[str] = []
    seen: set[str] = set()
    for raw in candidates:
        text = _clean(raw)
        if not text:
            continue
        values = [text]
        if "/" in text:
            values.append(Path(text).stem)
        for value in values:
            if value not in seen:
                seen.add(value)
                aliases.append(value)
    canonical = _canonical_asset_id(_entry_asset_id(entry))
    if canonical and canonical not in seen:
        aliases.append(canonical)
    return aliases


def _review_rubric_for_category(category: str) -> list[str]:
    normalized = _clean(category).lower()
    return ASSET_REVIEW_RUBRICS.get(
        normalized,
        [
            "asset category, story purpose, and visual_spec match the planned usage",
            "asset appears only in selectors allowed by the semantic contract",
            "asset is not used in an incompatible manifest category slot",
        ],
    )


def _wrong_category_usage(category: str, events: list[dict[str, str]]) -> list[dict[str, str]]:
    expected = _expected_usage_categories(category)
    if not expected:
        return []
    wrong: list[dict[str, str]] = []
    for event in events:
        usage_category = _clean(event.get("usage_category"))
        if usage_category in {"references", "assets"}:
            continue
        if usage_category not in expected:
            wrong.append(event)
    return wrong


def _expected_usage_categories(category: str) -> set[str]:
    normalized = _clean(category).lower()
    if normalized in {"characters", "character", "character_reference"}:
        return {"characters"}
    if normalized in {"objects", "object", "story_specific_items", "object_reference"}:
        return {"objects"}
    if normalized in {"locations", "location", "location_reference"}:
        return {"locations"}
    if normalized in {"setpieces", "setpiece", "setpiece_reference"}:
        return {"setpieces"}
    return set()


def _suggested_fix_targets(
    *,
    semantic_contract: dict[str, Any],
    planned_but_unused: bool,
    wrong_category_usage: list[dict[str, str]],
) -> list[str]:
    targets = ["asset_plan.md"]
    if planned_but_unused or wrong_category_usage:
        targets.append("video_manifest.md")
    if semantic_contract.get("must_appear_in_selectors") or semantic_contract.get("must_not_appear_in_selectors"):
        targets.append("image_generation_requests.md")
    return targets


def _iter_manifest_nodes(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for scene in _as_list(manifest.get("scenes")):
        if not isinstance(scene, dict):
            continue
        cuts = _as_list(scene.get("cuts"))
        if cuts:
            nodes.extend([cut for cut in cuts if isinstance(cut, dict)])
        else:
            nodes.append(scene)
    return nodes


def _extract_asset_ids(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [_clean(value.get("asset_id") or value.get("id") or value.get("selector"))]
    text = _clean(value)
    if not text:
        return []
    path_name = Path(text).stem if "/" in text else text
    return [text, path_name] if path_name != text else [text]


def _output_refs(
    run_dir: Path,
    *,
    plan_entry: dict[str, Any],
    request: dict[str, str],
    manifest_item: dict[str, Any],
) -> list[dict[str, Any]]:
    raw_paths: list[str] = []
    for raw in _as_list(plan_entry.get("existing_outputs")):
        if _clean(raw):
            raw_paths.append(_clean(raw))
    generation_plan = _entry_generation_plan(plan_entry)
    for source in (generation_plan, request, manifest_item):
        for key in ("output", "output_path", "savedPath", "path"):
            value = _clean(source.get(key))
            if value:
                raw_paths.append(value)

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rel in raw_paths:
        if rel in seen:
            continue
        seen.add(rel)
        path = Path(rel)
        resolved = path if path.is_absolute() else run_dir / path
        out.append({"path": rel, "exists": resolved.exists() and resolved.is_file()})
    return out


def _contact_sheet_refs(run_dir: Path) -> list[str]:
    roots = [run_dir / "logs" / "review" / "semantic", run_dir / "logs" / "review", run_dir / "assets"]
    suffixes = {".png", ".jpg", ".jpeg", ".webp"}
    refs: list[str] = []
    seen: set[str] = set()
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            lower_name = path.name.lower()
            if not path.is_file() or path.suffix.lower() not in suffixes:
                continue
            if "contact" in lower_name and "sheet" in lower_name:
                rel = _run_relative(run_dir, path)
                if rel not in seen:
                    seen.add(rel)
                    refs.append(rel)
    return refs


def _run_relative(run_dir: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(run_dir.resolve()))
    except ValueError:
        return str(path)
