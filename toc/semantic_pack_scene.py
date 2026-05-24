"""Scene and cut semantic review pack collectors."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from toc.harness import load_structured_document
from toc.immersive_manifest import make_scene_cut_selector


SUPPORTED_STAGES = {"scene_set", "scene_detail", "cut_blueprint"}


def collect_entries(
    stage: str,
    run_dir: Path,
    manifest: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Collect semantic-review-ready scene or cut entries for a run.

    The generic semantic pack builder calls this function with one of the
    supported scene/cut stages. `script.md` is the source of truth when present;
    `manifest` or `video_manifest.md` is used only as a fallback for tests and
    partially materialized runs.
    """

    if stage not in SUPPORTED_STAGES:
        raise ValueError(f"Unsupported scene semantic stage: {stage}")

    resolved_run_dir = Path(run_dir)
    source_path, data = _load_scene_source(resolved_run_dir, manifest)
    scenes = _extract_scenes(data)

    if stage in {"scene_set", "scene_detail"}:
        return [
            _scene_entry(stage=stage, scene=scene, scene_index=index, source_path=source_path)
            for index, scene in enumerate(scenes)
        ]

    return [
        _cut_entry(
            scene=scene,
            scene_index=scene_index,
            cut=cut,
            cut_index=cut_index,
            scene_cuts=[item for item in _list_value(scene.get("cuts")) if isinstance(item, dict)],
            source_path=source_path,
        )
        for scene_index, scene in enumerate(scenes)
        for cut_index, cut in enumerate(_list_value(scene.get("cuts")))
        if isinstance(cut, dict)
    ]


def _load_scene_source(run_dir: Path, manifest: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
    script_path = run_dir / "script.md"
    if script_path.exists():
        _, data = load_structured_document(script_path)
        return "script.md", data

    if manifest is not None:
        return "manifest", manifest

    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.exists():
        _, data = load_structured_document(manifest_path)
        return "video_manifest.md", data

    return "script.md", {}


def _extract_scenes(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        data.get("scenes"),
        _dict_value(data.get("script")).get("scenes"),
        data.get("scene_set"),
    ]
    for candidate in candidates:
        scenes = [scene for scene in _list_value(candidate) if isinstance(scene, dict)]
        if scenes:
            return scenes
    return []


def _scene_entry(
    *,
    stage: str,
    scene: dict[str, Any],
    scene_index: int,
    source_path: str,
) -> dict[str, Any]:
    scene_id = _text(scene.get("scene_id"), default=str(scene_index + 1))
    cuts = _list_value(scene.get("cuts"))
    semantic_contract = _scene_semantic_contract(scene)
    normalized_contract = _normalize_scene_contract(scene, semantic_contract)
    missing_fields = _missing_required_fields(
        normalized_contract,
        ("dramatic_question", "value_shift", "causal_turn", "done_when"),
    )
    entry: dict[str, Any] = {
        "stage": stage,
        "id": f"scene:{scene_id}",
        "selector": _scene_selector(scene_id),
        "canonical_selector": make_scene_cut_selector(scene_id),
        "source_path": source_path,
        "source_section": f"scenes[{scene_index}]",
        "source_json_pointer": f"/scenes/{scene_index}",
        "scene_id": scene_id,
        "phase": scene.get("phase"),
        "importance": scene.get("importance"),
        "summary": _scene_summary(scene),
        "semantic_contract": semantic_contract,
        "semantic_contract_present": bool(semantic_contract),
        "semantic_contract_missing": bool(missing_fields),
        "normalized_semantic_contract": normalized_contract,
        "contract_required_fields_missing": missing_fields,
        "scene_intent": scene.get("scene_intent"),
        "coverage_review": scene.get("coverage_review"),
        "handoff_to_next_scene": scene.get("handoff_to_next_scene"),
        "terminal_resolution": scene.get("terminal_resolution"),
        "cut_count": len(cuts),
    }
    if stage == "scene_detail":
        entry["cut_summaries"] = [
            _cut_summary(scene_id=scene_id, cut=cut, cut_index=cut_index)
            for cut_index, cut in enumerate(cuts)
            if isinstance(cut, dict)
        ]
    return _without_empty_values(entry)


def _cut_entry(
    *,
    scene: dict[str, Any],
    scene_index: int,
    cut: dict[str, Any],
    cut_index: int,
    scene_cuts: list[dict[str, Any]],
    source_path: str,
) -> dict[str, Any]:
    scene_id = _text(scene.get("scene_id"), default=str(scene_index + 1))
    cut_id = _text(cut.get("cut_id"), default=f"{cut_index + 1:02d}")
    selector = _text(cut.get("selector"), default=_cut_selector(scene_id, cut_id))
    blueprint = _dict_value(cut.get("cut_blueprint"))
    scene_contract = _dict_value(cut.get("scene_contract"))
    semantic_contract = cut.get("semantic_contract") or scene_contract or _contract_from_blueprint(blueprint)
    normalized_contract = _normalize_cut_contract(cut, semantic_contract, blueprint, scene_contract)
    missing_fields = _missing_required_fields(
        normalized_contract,
        ("target_beat", "must_show", "must_avoid", "done_when"),
    )

    return _without_empty_values(
        {
            "stage": "cut_blueprint",
            "id": f"cut:{selector}",
            "selector": selector,
            "canonical_selector": make_scene_cut_selector(scene_id, cut_id),
            "source_path": source_path,
            "source_section": f"scenes[{scene_index}].cuts[{cut_index}]",
            "source_json_pointer": f"/scenes/{scene_index}/cuts/{cut_index}",
            "scene_id": scene_id,
            "cut_id": cut_id,
            "summary": _text(
                blueprint.get("target_beat")
                or scene_contract.get("target_beat")
                or blueprint.get("visual_beat")
                or cut.get("visual_beat")
            ),
            "semantic_contract": semantic_contract,
            "semantic_contract_present": bool(semantic_contract),
            "semantic_contract_missing": bool(missing_fields),
            "normalized_semantic_contract": normalized_contract,
            "contract_required_fields_missing": missing_fields,
            "cut_blueprint": blueprint or None,
            "scene_contract": scene_contract or None,
            "asset_dependency_hint": blueprint.get("asset_dependency_hint"),
            "previous_cut_summary": _neighbor_cut_summary(scene_id=scene_id, cuts=scene_cuts, cut_index=cut_index - 1),
            "next_cut_summary": _neighbor_cut_summary(scene_id=scene_id, cuts=scene_cuts, cut_index=cut_index + 1),
            "human_review": cut.get("human_review"),
            "implementation_trace": cut.get("implementation_trace"),
        }
    )


def _scene_summary(scene: dict[str, Any]) -> str:
    intent = _dict_value(scene.get("scene_intent"))
    candidates = [
        intent.get("dramatic_question"),
        intent.get("value_shift"),
        intent.get("causal_turn"),
        scene.get("purpose"),
        scene.get("visualizable_action"),
        scene.get("narration"),
        scene.get("visual"),
    ]
    return " / ".join(_text(value) for value in candidates if _text(value))


def _scene_semantic_contract(scene: dict[str, Any]) -> Any:
    if scene.get("semantic_contract"):
        return scene.get("semantic_contract")
    if scene.get("scene_contract"):
        return scene.get("scene_contract")

    intent = _dict_value(scene.get("scene_intent"))
    contract: dict[str, Any] = {}
    for key in ("dramatic_question", "value_shift", "causal_turn"):
        if intent.get(key):
            contract[key] = intent[key]
    for key in ("handoff_to_next_scene", "terminal_resolution"):
        if scene.get(key):
            contract[key] = scene[key]
    return contract or None


def _normalize_scene_contract(scene: dict[str, Any], semantic_contract: Any) -> dict[str, Any]:
    contract = _dict_value(semantic_contract)
    scene_contract = _dict_value(scene.get("scene_contract"))
    intent = _dict_value(scene.get("scene_intent"))
    return _without_empty_values(
        {
            "dramatic_question": contract.get("dramatic_question")
            or scene_contract.get("dramatic_question")
            or intent.get("dramatic_question"),
            "value_shift": contract.get("value_shift") or scene_contract.get("value_shift") or intent.get("value_shift"),
            "causal_turn": contract.get("causal_turn") or scene_contract.get("causal_turn") or intent.get("causal_turn"),
            "done_when": contract.get("done_when") or scene_contract.get("done_when") or scene.get("done_when"),
        }
    )


def _normalize_cut_contract(
    cut: dict[str, Any],
    semantic_contract: Any,
    blueprint: dict[str, Any],
    scene_contract: dict[str, Any],
) -> dict[str, Any]:
    contract = _dict_value(semantic_contract)
    return _without_empty_values(
        {
            "target_beat": contract.get("target_beat")
            or scene_contract.get("target_beat")
            or blueprint.get("target_beat")
            or cut.get("target_beat")
            or cut.get("visual_beat"),
            "must_show": contract.get("must_show") or scene_contract.get("must_show") or blueprint.get("must_show"),
            "must_avoid": contract.get("must_avoid") or scene_contract.get("must_avoid") or blueprint.get("must_avoid"),
            "done_when": contract.get("done_when") or scene_contract.get("done_when") or blueprint.get("done_when"),
        }
    )


def _missing_required_fields(contract: dict[str, Any], required_fields: tuple[str, ...]) -> list[str]:
    return [field for field in required_fields if field not in contract]


def _contract_from_blueprint(blueprint: dict[str, Any]) -> dict[str, Any] | None:
    if not blueprint:
        return None
    keys = ("target_beat", "must_show", "must_avoid", "done_when", "visual_beat", "narration_role")
    contract = {key: blueprint[key] for key in keys if key in blueprint and blueprint[key] not in (None, "", [])}
    return contract or None


def _cut_summary(*, scene_id: str, cut: dict[str, Any], cut_index: int) -> dict[str, Any]:
    cut_id = _text(cut.get("cut_id"), default=f"{cut_index + 1:02d}")
    selector = _text(cut.get("selector"), default=_cut_selector(scene_id, cut_id))
    blueprint = _dict_value(cut.get("cut_blueprint"))
    scene_contract = _dict_value(cut.get("scene_contract"))
    return _without_empty_values(
        {
            "selector": selector,
            "cut_id": cut_id,
            "target_beat": blueprint.get("target_beat") or scene_contract.get("target_beat"),
            "visual_beat": blueprint.get("visual_beat") or cut.get("visual_beat"),
            "must_show": blueprint.get("must_show") or scene_contract.get("must_show"),
            "semantic_contract": cut.get("semantic_contract") or scene_contract or _contract_from_blueprint(blueprint),
        }
    )


def _neighbor_cut_summary(*, scene_id: str, cuts: list[dict[str, Any]], cut_index: int) -> dict[str, Any] | None:
    if cut_index < 0 or cut_index >= len(cuts):
        return None
    return _cut_summary(scene_id=scene_id, cut=cuts[cut_index], cut_index=cut_index)


def _scene_selector(scene_id: str) -> str:
    return f"scene{scene_id}"


def _cut_selector(scene_id: str, cut_id: str) -> str:
    normalized_cut = f"{int(cut_id):02d}" if cut_id.isdigit() else cut_id
    return f"scene{scene_id}_cut{normalized_cut}"


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text if text else default


def _without_empty_values(entry: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in entry.items() if value not in (None, "", [], {})}
