from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from toc.immersive_manifest import dotted_id_sort_key, normalize_dotted_id
SELECTOR_RE = re.compile(r"scene(?P<scene_id>\d+(?:\.\d+)?)(?:_cut(?P<cut_id>\d+(?:\.\d+)?))?", re.I)
REFERENCE_OUTPUT_PREFIXES = ("assets/characters/", "assets/objects/")
SUPPORTED_RULES = {"must_not_appear_before"}


@dataclass(frozen=True)
class RevealConstraint:
    subject_type: str
    subject_id: str
    rule: str
    selector: str
    rationale: str = ""


@dataclass(frozen=True)
class RevealViolation:
    subject_type: str
    subject_id: str
    rule: str
    selector: str
    scene_id: str
    cut_id: str
    evidence: tuple[str, ...]
    rationale: str = ""


def parse_selector(selector: str) -> tuple[str, str] | None:
    match = SELECTOR_RE.fullmatch(str(selector or "").strip())
    if not match:
        return None
    scene_id = normalize_dotted_id(match.group("scene_id"))
    cut_id = normalize_dotted_id(match.group("cut_id") or 0)
    if not scene_id or not cut_id:
        return None
    return scene_id, cut_id


def build_manifest_cut_order_map(manifest: dict[str, Any]) -> dict[tuple[str, str], int]:
    order: dict[tuple[str, str], int] = {}
    index = 0
    scenes = manifest.get("scenes")
    if not isinstance(scenes, list):
        return order
    sorted_scenes = sorted(
        [scene for scene in scenes if isinstance(scene, dict)],
        key=lambda scene: dotted_id_sort_key(scene.get("scene_id")),
    )
    for scene in sorted_scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = normalize_dotted_id(scene.get("scene_id"))
        if not scene_id:
            continue
        cuts = scene.get("cuts")
        if isinstance(cuts, list) and cuts:
            sorted_cuts = sorted(
                [cut for cut in cuts if isinstance(cut, dict)],
                key=lambda cut: dotted_id_sort_key(cut.get("cut_id")),
            )
            for cut in sorted_cuts:
                if not isinstance(cut, dict):
                    continue
                cut_id = normalize_dotted_id(cut.get("cut_id"))
                if not cut_id:
                    continue
                order[(scene_id, cut_id)] = index
                index += 1
            continue
        order[(scene_id, "0")] = index
        index += 1
    return order


def load_reveal_constraints(script_data: dict[str, Any]) -> list[RevealConstraint]:
    contract = script_data.get("evaluation_contract") if isinstance(script_data.get("evaluation_contract"), dict) else {}
    raw_constraints = contract.get("reveal_constraints") if isinstance(contract, dict) else None
    if not isinstance(raw_constraints, list):
        return []
    constraints: list[RevealConstraint] = []
    for item in raw_constraints:
        if not isinstance(item, dict):
            continue
        subject_type = _normalize_subject_type(item.get("subject_type"))
        subject_id = str(item.get("subject_id") or "").strip()
        rule = str(item.get("rule") or "").strip().lower()
        selector = str(item.get("selector") or "").strip()
        rationale = str(item.get("rationale") or "").strip()
        if not subject_type or not subject_id or rule not in SUPPORTED_RULES or not parse_selector(selector):
            continue
        constraints.append(
            RevealConstraint(
                subject_type=subject_type,
                subject_id=subject_id,
                rule=rule,
                selector=selector,
                rationale=rationale,
            )
        )
    return constraints


def build_asset_aliases(manifest: dict[str, Any]) -> dict[str, dict[str, set[str]]]:
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), dict) else {}
    result = {"character": {}, "object": {}}
    for kind, field in (("character", "character_bible"), ("object", "object_bible")):
        for asset in assets.get(field, []) if isinstance(assets, dict) else []:
            if not isinstance(asset, dict):
                continue
            asset_id = asset.get(f"{kind}_id")
            if not isinstance(asset_id, str) or not asset_id.strip():
                continue
            aliases: set[str] = {asset_id}
            for extra_key in ("review_aliases", "aliases"):
                values = asset.get(extra_key)
                if isinstance(values, list):
                    aliases.update(str(v).strip() for v in values if str(v).strip())
            for name_key in ("display_name", "name"):
                if isinstance(asset.get(name_key), str):
                    aliases.add(str(asset.get(name_key)).strip())
            result[kind][asset_id] = {alias for alias in aliases if alias}
    return result


def find_reveal_violations_for_surface(
    *,
    scene_id: int,
    cut_id: int,
    output: str,
    text_fragments: list[str],
    declared_character_ids: set[str],
    declared_object_ids: set[str],
    constraints: list[RevealConstraint],
    aliases: dict[str, dict[str, set[str]]],
    cut_order_map: dict[tuple[int, int], int],
    skip_reference_outputs: bool = True,
) -> list[RevealViolation]:
    if skip_reference_outputs and is_reference_output(output):
        return []
    node_order = cut_order_map.get((scene_id, cut_id))
    if node_order is None:
        return []

    violations: list[RevealViolation] = []
    for constraint in constraints:
        selector_key = parse_selector(constraint.selector)
        if selector_key is None:
            continue
        selector_order = cut_order_map.get(selector_key)
        if selector_order is None or node_order >= selector_order:
            continue

        evidence: list[str] = []
        declared_ids = declared_character_ids if constraint.subject_type == "character" else declared_object_ids
        if constraint.subject_id in declared_ids:
            field_name = "character_ids" if constraint.subject_type == "character" else "object_ids"
            evidence.append(f"{field_name} includes `{constraint.subject_id}`")

        alias_hits = sorted(
            alias
            for alias in _subject_aliases(aliases, constraint.subject_type, constraint.subject_id)
            if alias and any(alias in fragment for fragment in text_fragments if fragment)
        )
        if alias_hits:
            evidence.append(f"text mentions {alias_hits!r}")

        if evidence:
            violations.append(
                RevealViolation(
                    subject_type=constraint.subject_type,
                    subject_id=constraint.subject_id,
                    rule=constraint.rule,
                    selector=constraint.selector,
                    scene_id=scene_id,
                    cut_id=cut_id,
                    evidence=tuple(evidence),
                    rationale=constraint.rationale,
                )
            )
    return violations


def is_reference_output(output: str) -> bool:
    normalized = str(output or "").replace("\\", "/")
    return normalized.startswith(REFERENCE_OUTPUT_PREFIXES)


def _normalize_subject_type(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"character", "characters"}:
        return "character"
    if normalized in {"object", "objects", "setpiece", "artifact"}:
        return "object"
    return ""


def _subject_aliases(aliases: dict[str, dict[str, set[str]]], subject_type: str, subject_id: str) -> set[str]:
    subject_aliases = ((aliases or {}).get(subject_type) or {}).get(subject_id)
    if isinstance(subject_aliases, set) and subject_aliases:
        return set(subject_aliases)
    return {subject_id}
