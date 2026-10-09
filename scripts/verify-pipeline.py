#!/usr/bin/env python3
"""Verify ToC production artifacts with deterministic structural checks.

The verifier is deliberately limited to ordinary file, schema, identity,
reference, provider provenance, and media checks. It does not run reviewers,
calculate scores, require review reports, or write approval state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from PIL import Image  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover - optional diagnostic only
    Image = None


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import (  # noqa: E402
    append_state_snapshot,
    eval_report_path,
    load_structured_document,
    now_iso,
    parse_state_file,
    run_report_path,
    sync_run_status,
    write_json,
)
from toc.image_request_snapshot import (  # noqa: E402
    ImageRequestSnapshotError,
    current_reference_sha256s,
    load_request_snapshot,
)
from toc.stage_evaluation import pipeline as pipeline_policy  # noqa: E402
from toc.stage_evaluation.common import (  # noqa: E402
    add_check,
    as_dict,
    as_list,
    nested_get,
    non_empty,
)
from toc.stage_evaluation.manifest import (  # noqa: E402
    _iter_manifest_nodes,
    check_manifest_single as shared_check_manifest_single,
)
from toc.script_narration import is_b_roll, resolve_manifest_narration
from toc.stage_evaluator import check_visual_value  # noqa: E402


VECTOR_GATE_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
REQUEST_SNAPSHOT_FILE_BY_KIND = {
    "asset": "asset_generation_request_snapshot.json",
    "scene": "image_generation_request_snapshot.json",
}


def _safe_run_file(run_dir: Path, value: Any) -> Path | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    candidate = Path(raw)
    if candidate.is_absolute():
        return None
    try:
        resolved = (run_dir / candidate).resolve()
        resolved.relative_to(run_dir.resolve())
    except ValueError:
        return None
    return resolved


def _read_regular_run_bytes(run_dir: Path, value: Any) -> bytes:
    path = _safe_run_file(run_dir, value)
    if path is None:
        raise ValueError("path escapes run directory")
    if path.is_symlink() or not path.is_file():
        raise ValueError("path is not a regular file")
    return path.read_bytes()


def _normalized_run_relative_path(run_dir: Path, value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    path = Path(raw)
    try:
        candidate = path if path.is_absolute() else run_dir / path
        return candidate.resolve().relative_to(run_dir.resolve()).as_posix()
    except ValueError:
        return None


def _is_regular_run_relative_file_no_follow(run_dir: Path, value: Any) -> bool:
    path = _safe_run_file(run_dir, value)
    return bool(path and not path.is_symlink() and path.is_file())


def _state_list_values(state: dict[str, str], key: str) -> list[str]:
    raw = str(state.get(key) or "").strip()
    if not raw:
        return []
    return [value for item in raw.split(",") if (value := item.strip().strip("`\"'"))]


def _manifest_data_for_outputs(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "video_manifest.md"
    return load_structured_document(path)[1] if path.is_file() else {}


def _node_output_paths(run_dir: Path, *, field_path: list[str]) -> list[Path]:
    outputs: list[Path] = []
    for node in _iter_manifest_nodes(_manifest_data_for_outputs(run_dir)):
        value: Any = node
        for key in field_path:
            value = value.get(key) if isinstance(value, dict) else None
        if not non_empty(value):
            continue
        path = _safe_run_file(run_dir, value)
        if path is not None:
            outputs.append(path)
    return outputs


def _existing_media_files(path: Path, suffixes: set[str]) -> list[Path]:
    if not path.is_dir():
        return []
    return [item for item in path.rglob("*") if item.is_file() and not item.is_symlink() and item.suffix.lower() in suffixes]


def _image_generation_provenance_by_destination(run_dir: Path) -> dict[str, dict[str, Any]]:
    log_path = run_dir / "logs" / "image_generation_prompts.jsonl"
    if not log_path.is_file():
        return {}
    records: dict[str, dict[str, Any]] = {}
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and str(payload.get("destination") or "").strip():
            records[str(payload["destination"]).strip()] = payload
    return records


def _image_generation_provenance_failures(
    run_dir: Path,
    outputs: list[str],
    *,
    provenance: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    records = provenance if provenance is not None else _image_generation_provenance_by_destination(run_dir)
    failures: list[str] = []
    for output in outputs:
        destination = str(output or "").strip()
        if not destination:
            continue
        record = records.get(destination)
        if not record:
            failures.append(f"{destination}: missing app-server generation provenance")
            continue
        status = str(record.get("status") or "").strip().lower()
        if status not in {"completed", "success", "succeeded"}:
            failures.append(f"{destination}: generation status {status or '(missing)'}")
        if not str(record.get("savedPath") or "").strip():
            failures.append(f"{destination}: missing savedPath in generation provenance")
    return failures


def _strict_snapshot_provenance_record_matches(
    run_dir: Path,
    *,
    snapshot: Any,
    item: Any,
    payload: dict[str, Any],
) -> bool:
    del snapshot
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    if str(payload.get("status") or "").strip().lower() not in {"completed", "succeeded"}:
        return False
    if str(payload.get("itemId") or "") != str(item.item_id):
        return False
    if str(payload.get("kind") or "") != str(item.kind):
        return False
    if _normalized_run_relative_path(run_dir, payload.get("destination")) != item.destination:
        return False
    if str(payload.get("apiPromptPolicyVersion") or "") != item.prompt_policy_version:
        return False
    if str(payload.get("source") or "") != "app_server":
        return False
    if str(provenance.get("policy") or "") != "request_bound_v2" or provenance.get("authoritative") is not True:
        return False
    if str(provenance.get("itemId") or "") != item.item_id:
        return False
    for field in ("generationJobId", "turnId", "imageGenerationItemId", "savedPath"):
        if not str(provenance.get(field) or "").strip():
            return False
    try:
        if int(provenance.get("imageGenerationItemCount") or 0) != 1:
            return False
    except (TypeError, ValueError):
        return False
    if _normalized_run_relative_path(run_dir, provenance.get("destination")) != item.destination:
        return False
    if str(provenance.get("promptSha256") or "") != item.prompt_sha256:
        return False
    try:
        if list(provenance.get("referenceSha256s") or []) != list(current_reference_sha256s(run_dir, item)):
            return False
    except (ImageRequestSnapshotError, OSError, ValueError):
        return False
    for field, expected in (
        ("requestDigest", item.request_digest),
        ("compilerVersion", item.compiler_version),
        ("sourceDigest", item.source_digest),
    ):
        if str(provenance.get(field) or "") != expected:
            return False
    try:
        output_sha = hashlib.sha256(_read_regular_run_bytes(run_dir, item.destination)).hexdigest()
    except (OSError, ValueError):
        return False
    return str(provenance.get("outputSha256") or "") == output_sha and str(payload.get("outputSha256") or "") == output_sha


def _strict_snapshot_provenance_failures(
    run_dir: Path,
    *,
    kind: str,
    expected_outputs: list[str] | None = None,
    excluded_item_ids: set[str] | None = None,
) -> list[str]:
    filename = REQUEST_SNAPSHOT_FILE_BY_KIND[kind]
    path = run_dir / filename
    if not path.is_file():
        return [f"{filename}: immutable request snapshot is missing"]
    try:
        snapshot = load_request_snapshot(path, run_dir=run_dir, verify_references=True)
    except ImageRequestSnapshotError as exc:
        return [f"{filename}: current snapshot validation failed: {exc}"]
    if snapshot.kind != kind:
        return [f"{filename}: expected kind {kind}, got {snapshot.kind}"]
    failures: list[str] = []
    destinations = {item.destination for item in snapshot.items}
    for raw_output in expected_outputs or []:
        output = _normalized_run_relative_path(run_dir, raw_output)
        if output and output not in destinations:
            failures.append(f"{output}: missing from current immutable request snapshot")
    excluded = excluded_item_ids or set()
    unknown = excluded - {item.item_id for item in snapshot.items}
    if unknown:
        failures.append("excluded provenance item ids are absent from the current snapshot: " + ", ".join(sorted(unknown)))
    log_dir = run_dir / "logs" / "app_server" / "image_gen"
    payloads: list[dict[str, Any]] = []
    if log_dir.is_dir():
        for log_path in sorted(log_dir.glob("*.json"), reverse=True):
            try:
                payload = json.loads(log_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                payloads.append(payload)
    for item in snapshot.items:
        if item.item_id in excluded:
            continue
        if not any(_strict_snapshot_provenance_record_matches(run_dir, snapshot=snapshot, item=item, payload=payload) for payload in payloads):
            failures.append(f"{item.destination}: no strict request_bound_v2 provenance matches the current per-item snapshot digest and bytes")
    return failures


def _asset_entries(asset_plan: dict[str, Any]) -> list[dict[str, Any]]:
    assets = asset_plan.get("assets")
    if isinstance(assets, list):
        return [item for item in assets if isinstance(item, dict)]
    if not isinstance(assets, dict):
        return []
    entries: list[dict[str, Any]] = []
    for category in ("characters", "objects", "locations", "setpieces", "reusable_stills"):
        for item in as_list(assets.get(category)):
            if isinstance(item, dict):
                copied = dict(item)
                copied.setdefault("_category", category)
                entries.append(copied)
    return entries


def _entry_generation_plan(entry: dict[str, Any]) -> dict[str, Any]:
    value = entry.get("generation_plan")
    return value if isinstance(value, dict) else {}


def _entry_asset_id(entry: dict[str, Any]) -> str:
    return str(entry.get("asset_id") or "").strip()


def _entry_asset_type(entry: dict[str, Any]) -> str:
    return str(entry.get("asset_type") or "").strip()


def _entry_required_views(entry: dict[str, Any]) -> list[str]:
    return [str(item).strip().lower() for item in as_list(_entry_generation_plan(entry).get("required_views")) if str(item).strip()]


def _entry_reference_inputs(entry: dict[str, Any]) -> list[str]:
    return [str(item).strip() for item in as_list(_entry_generation_plan(entry).get("reference_inputs")) if str(item).strip()]


def _entry_outputs(entry: dict[str, Any]) -> list[str]:
    outputs = [str(item).strip() for item in as_list(entry.get("existing_outputs")) if str(item).strip()]
    plan = _entry_generation_plan(entry)
    for key in ("output", "output_path"):
        value = str(plan.get(key) or "").strip()
        if value and value not in outputs:
            outputs.append(value)
    return outputs


def _request_sections_by_asset_id(text: str) -> dict[str, dict[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading or lines:
                sections.append((heading, lines))
            heading, lines = line[3:].strip(), []
        else:
            lines.append(line)
    if heading or lines:
        sections.append((heading, lines))
    fields_re = re.compile(r"^\s*-\s+([A-Za-z0-9_.]+):\s*(.*?)\s*$")
    result: dict[str, dict[str, str]] = {}
    for heading, lines in sections:
        fields: dict[str, str] = {}
        fenced: list[str] = []
        for line in lines:
            if line.strip().startswith("```"):
                fenced.append(line.strip()[3:].strip().lower())
            match = fields_re.match(line)
            if match:
                value = match.group(2).strip()
                if value.startswith("`") and value.endswith("`"):
                    value = value[1:-1]
                fields[match.group(1)] = value
        fields["__fenced_labels"] = ",".join(item for item in fenced if item)
        asset_id = (fields.get("asset_id") or heading).strip("` ")
        if asset_id:
            result[asset_id] = fields
    return result


def _request_field_value(fields: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(fields.get(key) or "").strip()
        if value:
            return value
    return ""


def _parse_int_field(value: str) -> int | None:
    try:
        return int(str(value or "").strip("` "))
    except (TypeError, ValueError):
        return None


def _asset_inventory_schema_issues(inventory_root: Any) -> list[str]:
    if not isinstance(inventory_root, dict):
        return ["asset_inventory root missing"]
    issues: list[str] = []
    if not isinstance(inventory_root.get("source_artifacts"), list):
        issues.append("source_artifacts[] missing")
    scope = inventory_root.get("coverage_scope")
    if not isinstance(scope, dict):
        issues.append("coverage_scope missing")
    else:
        for key in ("characters", "story_specific_items", "locations", "setpieces", "reusable_stills"):
            if not isinstance(scope.get(key), list):
                issues.append(f"coverage_scope.{key}[] missing")
    items = inventory_root.get("items")
    if not isinstance(items, list):
        issues.append("items[] missing")
    else:
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                issues.append(f"items[{index}] is not mapping")
                continue
            for key in ("item_id", "category", "source_script_selectors", "story_purpose", "recommended_asset_type"):
                if key == "source_script_selectors":
                    if not isinstance(item.get(key), list):
                        issues.append(f"items[{index}].{key}[] missing")
                elif not str(item.get(key) or "").strip():
                    issues.append(f"items[{index}].{key} missing")
    return issues


def _output_exists(run_dir: Path, rel: str) -> bool:
    return _is_regular_run_relative_file_no_follow(run_dir, rel)


def check_asset(run_dir: Path, *, target_slot: str = "p570") -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    target_number = pipeline_policy._slot_number(target_slot, default=570)
    inventory_path = run_dir / "asset_inventory.md"
    plan_path = run_dir / "asset_plan.md"
    request_path = run_dir / "asset_generation_requests.md"
    manifests = [run_dir / "asset_generation_manifest.md", run_dir / "location_asset_generation_manifest.md"]
    add_check(checks, "asset.asset_inventory", target_number < 520 or inventory_path.is_file(), f"{inventory_path.name} exists")
    add_check(checks, "asset.asset_plan", target_number < 530 or plan_path.is_file(), f"{plan_path.name} exists")
    add_check(checks, "asset.generation_requests", target_number < 550 or request_path.is_file(), f"{request_path.name} exists")

    inventory_text, inventory_data = _document_if_file(inventory_path)
    inventory_root = inventory_data.get("asset_inventory") if isinstance(inventory_data.get("asset_inventory"), dict) else inventory_data
    inventory_issues = _asset_inventory_schema_issues(inventory_root)
    details["asset_inventory_item_count"] = len(as_list(inventory_root.get("items"))) if isinstance(inventory_root, dict) else 0
    if inventory_issues:
        details["asset_inventory_schema_issues"] = inventory_issues[:20]
    add_check(checks, "asset.inventory_structured", target_number < 520 or bool(inventory_data), "asset_inventory.md contains structured data")
    add_check(checks, "asset.inventory_schema", target_number < 520 or not inventory_issues, "asset inventory has typed source/scope/item fields")

    plan_text, plan_data = _document_if_file(plan_path)
    entries = _asset_entries(plan_data)
    details["asset_plan_entry_count"] = len(entries)
    plan_declared = isinstance(plan_data.get("assets"), (list, dict))
    add_check(checks, "asset.plan_structured", target_number < 530 or plan_declared, "asset_plan.md has structured asset entries")
    required_scope = {
        str(value).strip()
        for key in ("characters", "story_specific_items", "locations")
        for value in as_list(inventory_root.get("coverage_scope").get(key) if isinstance(inventory_root, dict) and isinstance(inventory_root.get("coverage_scope"), dict) else [])
        if str(value).strip()
    }
    planned_ids = {_entry_asset_id(entry) for entry in entries if _entry_asset_id(entry)}
    missing_scope = sorted(required_scope - planned_ids)
    add_check(checks, "asset.plan_covers_inventory_scope", target_number < 530 or not missing_scope, "asset plan covers declared inventory scope" + (f" (missing: {','.join(missing_scope[:8])})" if missing_scope else ""))
    malformed = []
    for entry in entries:
        asset_id = _entry_asset_id(entry) or "<missing_asset_id>"
        if not _entry_asset_id(entry) or not _entry_asset_type(entry) or not isinstance(entry.get("source_script_selectors"), list) or not isinstance(entry.get("generation_plan"), dict):
            malformed.append(asset_id)
    add_check(checks, "asset.required_fields", target_number < 530 or (not entries or not malformed), "asset plan entries have IDs, source selectors, type, and generation plan" + (f" (invalid: {','.join(malformed[:8])})" if malformed else ""))
    view_failures = [
        _entry_asset_id(entry) or "<missing_asset_id>"
        for entry in entries
        if "character" in _entry_asset_type(entry) and not {"front", "side", "back"}.issubset(set(_entry_required_views(entry)))
    ]
    add_check(checks, "asset.character_views", target_number < 530 or not view_failures, "character assets declare required reference views" + (f" (invalid: {','.join(view_failures[:8])})" if view_failures else ""))
    lane_failures: list[str] = []
    for entry in entries:
        asset_id = _entry_asset_id(entry) or "<missing_asset_id>"
        plan = _entry_generation_plan(entry)
        refs = _entry_reference_inputs(entry)
        lane = str(plan.get("execution_lane") or entry.get("execution_lane") or "").strip()
        derived = str(plan.get("derived_from_asset_id") or "").strip()
        if refs or derived:
            if lane and lane != "standard":
                lane_failures.append(f"{asset_id}:execution_lane")
        elif lane and lane != "bootstrap_builtin":
            lane_failures.append(f"{asset_id}:execution_lane")
    add_check(checks, "asset.lane_consistency", target_number < 530 or not lane_failures, "asset execution lanes match declared references" + (f" (invalid: {','.join(lane_failures[:8])})" if lane_failures else ""))

    planned_outputs: list[str] = []
    output_failures: list[str] = []
    for entry in entries:
        asset_id = _entry_asset_id(entry) or "<missing_asset_id>"
        outputs = _entry_outputs(entry)
        planned_outputs.extend(outputs)
        missing = [value for value in outputs if not _output_exists(run_dir, value)]
        if target_number >= 560 and (not outputs or missing):
            output_failures.append(f"{asset_id}:missing {','.join(missing[:3]) or 'output'}")
    add_check(checks, "asset.output_files", target_number < 560 or (not entries or not output_failures), "planned asset outputs exist" + (f" (issues: {','.join(output_failures[:8])})" if output_failures else ""))
    if target_number >= 560 and planned_outputs:
        snapshot = run_dir / REQUEST_SNAPSHOT_FILE_BY_KIND["asset"]
        provenance_failures = _strict_snapshot_provenance_failures(run_dir, kind="asset", expected_outputs=planned_outputs) if snapshot.is_file() else _image_generation_provenance_failures(run_dir, planned_outputs)
        if provenance_failures:
            details["asset_generation_provenance_failures"] = provenance_failures[:20]
        add_check(checks, "asset.generation_provenance", not provenance_failures, "asset outputs match request-bound provider provenance")
    request_text = request_path.read_text(encoding="utf-8") if request_path.is_file() else ""
    request_sections = _request_sections_by_asset_id(request_text)
    metadata_failures: list[str] = []
    if target_number >= 550:
        for entry in entries:
            asset_id = _entry_asset_id(entry)
            fields = request_sections.get(asset_id)
            if not fields:
                metadata_failures.append(f"{asset_id}:missing request section")
                continue
            for key in ("tool", "asset_type", "execution_lane", "reference_count", "output"):
                if not _request_field_value(fields, key):
                    metadata_failures.append(f"{asset_id}:missing {key}")
            if _request_field_value(fields, "tool") not in {"", "codex_builtin_image"}:
                metadata_failures.append(f"{asset_id}:tool")
    add_check(checks, "asset.request_metadata", target_number < 550 or (bool(entries) and not metadata_failures), "asset request metadata has structural fields" + (f" (issues: {','.join(metadata_failures[:8])})" if metadata_failures else ""))
    manifest_items: list[dict[str, Any]] = []
    for manifest_path in manifests:
        if manifest_path.is_file():
            manifest_items.extend(_asset_manifest_items(_document_if_file(manifest_path)[1]))
    manifest_ids = {_asset_manifest_item_id(item) for item in manifest_items if _asset_manifest_item_id(item)}
    missing_manifest_ids = sorted(planned_ids - manifest_ids)
    add_check(checks, "asset.manifest_items", target_number < 550 or (not entries or (bool(manifest_items) and not missing_manifest_ids)), "asset generation manifest covers planned IDs" + (f" (missing: {','.join(missing_manifest_ids[:8])})" if missing_manifest_ids else ""))
    generated_files = _existing_media_files(run_dir / "assets", VECTOR_GATE_IMAGE_SUFFIXES)
    add_check(checks, "asset.generated_or_manifested", target_number < 550 or not entries or bool(generated_files) or bool(manifest_items), "asset outputs or manifests are present")
    details["generated_asset_file_count"] = len(generated_files)
    return pipeline_policy.make_stage("asset", "asset_inventory.md / asset_plan.md / asset_generation_requests.md", checks, details=details), {}


def _document_if_file(path: Path) -> tuple[str, dict[str, Any]]:
    return load_structured_document(path) if path.is_file() else ("", {})


def _asset_manifest_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    root = data.get("asset_generation_manifest")
    if isinstance(root, dict) and isinstance(root.get("items"), list):
        return [item for item in root["items"] if isinstance(item, dict)]
    for key in ("assets", "items"):
        if isinstance(data.get(key), list):
            return [item for item in data[key] if isinstance(item, dict)]
    return []


def _asset_manifest_item_id(item: dict[str, Any]) -> str:
    return str(item.get("asset_id") or item.get("selector") or "").strip()


def check_image(run_dir: Path, *, target_slot: str = "p600") -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    target_number = pipeline_policy._slot_number(target_slot, default=680)
    request_path = run_dir / "image_generation_requests.md"
    request_text = request_path.read_text(encoding="utf-8") if request_path.is_file() else ""
    sections = _request_sections_by_asset_id(request_text)
    add_check(checks, "image.generation_requests", request_path.is_file(), f"{request_path.name} exists")
    tool_failures = [selector for selector, fields in sections.items() if _request_field_value(fields, "tool") not in {"", "codex_builtin_image"}]
    add_check(checks, "image.request_tool", not tool_failures, "image requests use the declared provider tool" + (f" (invalid: {','.join(tool_failures[:8])})" if tool_failures else ""))
    lane_failures: list[str] = []
    for selector, fields in sections.items():
        count = _parse_int_field(_request_field_value(fields, "reference_count"))
        lane = _request_field_value(fields, "execution_lane")
        if count is None or not lane:
            continue
        expected = "standard" if count > 0 else "bootstrap_builtin"
        if lane != expected:
            lane_failures.append(selector)
    add_check(checks, "image.request_lane", not lane_failures, "image request lanes match reference counts" + (f" (invalid: {','.join(lane_failures[:8])})" if lane_failures else ""))
    expected_outputs = [str(path.relative_to(run_dir)) for path in _node_output_paths(run_dir, field_path=["image_generation", "output"])]
    add_check(checks, "image.expected_outputs", bool(expected_outputs), "manifest declares image output paths")
    missing = [value for value in expected_outputs if not _output_exists(run_dir, value)]
    add_check(checks, "image.output_files", bool(expected_outputs) and not missing, "declared image outputs exist" + (f" (missing: {','.join(missing[:8])})" if missing else ""))
    if missing:
        details["missing_image_outputs"] = missing[:20]
    snapshot = run_dir / REQUEST_SNAPSHOT_FILE_BY_KIND["scene"]
    provenance_failures = _strict_snapshot_provenance_failures(run_dir, kind="scene", expected_outputs=expected_outputs) if snapshot.is_file() else _image_generation_provenance_failures(run_dir, expected_outputs)
    if provenance_failures:
        details["image_generation_provenance_failures"] = provenance_failures[:20]
    add_check(checks, "image.generation_provenance", not provenance_failures, "image outputs match request-bound provider provenance")
    return pipeline_policy.make_stage("image", "image_generation_requests.md / assets/scenes/**", checks, details=details), {}


def check_narration(run_dir: Path) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    expected_outputs = [str(path.relative_to(run_dir)) for path in _node_output_paths(run_dir, field_path=["audio", "narration", "output"])]
    missing = [value for value in expected_outputs if not _output_exists(run_dir, value)]
    nodes = _iter_manifest_nodes(_manifest_data_for_outputs(run_dir))
    optional_silent = [
        node for node in nodes
        if is_b_roll(node)
        and (resolve_manifest_narration(node) or {}).get("tool") == "silent"
        and as_dict((resolve_manifest_narration(node) or {}).get("silence_contract")).get("intentional") is True
    ]
    has_audio_or_optional_silence = bool(expected_outputs) or bool(nodes) and len(optional_silent) == len(nodes)
    add_check(checks, "narration.expected_outputs", has_audio_or_optional_silence, "manifest declares narration audio outputs or audio-free B-roll")
    add_check(checks, "narration.output_files", has_audio_or_optional_silence and not missing, "declared narration audio outputs exist; B-roll may omit audio" + (f" (missing: {','.join(missing[:8])})" if missing else ""))
    if missing:
        details["missing_audio_outputs"] = missing[:20]
    details["declared_audio_outputs"] = len(expected_outputs)
    return pipeline_policy.make_stage("narration", "assets/audio/**", checks, details=details), {}


def _video_checks(checks: list[dict[str, Any]], *, video_path: Path, state: dict[str, str], run_dir: Path) -> None:
    pipeline_policy.append_video_checks(checks, video_path=video_path, state=state, run_dir=run_dir, duration_probe=pipeline_policy._probe_duration)


def check_video_single(run_dir: Path, *, target_slot: str = "p930") -> tuple[dict[str, Any], dict[str, str]]:
    return pipeline_policy.check_video_single(run_dir, target_slot=target_slot)


def check_video_scene_series(run_dir: Path, *, target_slot: str = "p930") -> tuple[dict[str, Any], dict[str, str]]:
    return pipeline_policy.check_video_scene_series(run_dir, target_slot=target_slot)


TERMINAL_SLOT_STATUSES = {"done", "skipped", "awaiting_approval"}


def _slot_number_from_code(value: Any) -> int | None:
    match = re.fullmatch(r"p(\d{3})", str(value or "").strip())
    return int(match.group(1)) if match else None


def _is_slot_in_bucket(slot: Any, bucket: str) -> bool:
    slot_number = _slot_number_from_code(slot)
    bucket_number = _slot_number_from_code(bucket)
    return slot_number is not None and bucket_number is not None and bucket_number <= slot_number <= bucket_number + 99


def _required_orchestration_buckets(stage_target: str) -> list[str]:
    value = _slot_number_from_code(stage_target) or 930
    if value < 100:
        return []
    terminal = min(900, max(100, (value // 100) * 100))
    return [f"p{bucket}" for bucket in range(100, terminal + 1, 100)]


def _progress_has_event(progress_text: str, *, bucket: str, event: str) -> bool:
    for line in progress_text.splitlines():
        cells = [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]
        if len(cells) >= 4 and cells[1] == bucket and cells[3] == event:
            return True
    return False


def _relative_required_artifact_path(run_dir: Path, value: Any) -> tuple[Path | None, str]:
    path = _safe_run_file(run_dir, value)
    return (path, str(path.relative_to(run_dir)) if path else str(value or "<missing>"))


def _supervisor_result_issues(path: Path, *, run_dir: Path, bucket: str, state: dict[str, str], stage_target: str) -> list[str]:
    if not path.is_file():
        return [f"{bucket}:result_missing"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"{bucket}:result_invalid_json"]
    if not isinstance(payload, dict):
        return [f"{bucket}:result_invalid_json"]
    issues: list[str] = []
    if payload.get("bucket") != bucket:
        issues.append(f"{bucket}:result_bucket_mismatch")
    status = payload.get("status")
    if status not in {"done", "pending"}:
        issues.append(f"{bucket}:result_status_invalid")
    completed = payload.get("completed_slots")
    if not isinstance(completed, list) or not completed:
        issues.append(f"{bucket}:completed_slots_missing")
    else:
        if not all(_is_slot_in_bucket(slot, bucket) for slot in completed):
            issues.append(f"{bucket}:completed_slots_outside_bucket")
        for slot in completed:
            if state.get(f"slot.{slot}.status") not in TERMINAL_SLOT_STATUSES:
                issues.append(f"{bucket}:completed_slot_not_terminal:{slot}")
    required = payload.get("required_artifacts")
    if not isinstance(required, list) or not required:
        issues.append(f"{bucket}:required_artifacts_missing")
    else:
        for item in required:
            if not isinstance(item, dict):
                issues.append(f"{bucket}:required_artifact_invalid")
                continue
            required_path, display = _relative_required_artifact_path(run_dir, item.get("path"))
            if required_path is None or item.get("exists") is False or not required_path.is_file():
                issues.append(f"{bucket}:required_artifact_not_found:{display}")
    state_keys = payload.get("state_keys")
    if not isinstance(state_keys, dict) or not state_keys:
        issues.append(f"{bucket}:state_keys_missing")
    else:
        for key, value in state_keys.items():
            if not isinstance(key, str) or state.get(key) != str(value):
                issues.append(f"{bucket}:state_key_mismatch:{key}")
    return issues


def check_orchestration(run_dir: Path, *, stage_target: str) -> tuple[dict[str, Any], dict[str, str]]:
    checks: list[dict[str, Any]] = []
    state = parse_state_file(run_dir / "state.txt")
    buckets = _required_orchestration_buckets(stage_target)
    progress_path = run_dir / "logs" / "orchestration" / "l2_supervisor_progress.md"
    progress = progress_path.read_text(encoding="utf-8") if progress_path.is_file() else ""
    add_check(checks, "orchestration.progress_memo", progress_path.is_file(), f"{progress_path.relative_to(run_dir)} exists")
    missing_invocations = [bucket for bucket in buckets if not _progress_has_event(progress, bucket=bucket, event="invoked")]
    add_check(checks, "orchestration.l2_invoked", not missing_invocations, "all required supervisor invocation events are present" + (f" (missing: {','.join(missing_invocations)})" if missing_invocations else ""))
    state_issues = [bucket for bucket in buckets if state.get(f"orchestration.{bucket}.supervisor.call_status") not in {"returned", ""}]
    add_check(checks, "orchestration.state_terminal", not state_issues, "supervisor lifecycle state is structurally valid" + (f" (issues: {','.join(state_issues)})" if state_issues else ""))
    result_issues: list[str] = []
    for bucket in buckets:
        result_issues.extend(_supervisor_result_issues(run_dir / "logs" / "orchestration" / f"{bucket}.supervisor_result.json", run_dir=run_dir, bucket=bucket, state=state, stage_target=stage_target))
    add_check(checks, "orchestration.supervisor_results", not result_issues, "supervisor result files are structurally valid" + (f" (issues: {','.join(result_issues[:8])})" if result_issues else ""))
    return pipeline_policy.make_stage("orchestration", "logs/orchestration/l2_supervisor_progress.md / logs/orchestration/pXXX.supervisor_result.json", checks, details={"required_buckets": buckets}), {}


STAGE_TARGETS: dict[str, list[str]] = {
    "p130": ["research"],
    "p230": ["research", "story"],
    "p330": ["research", "story", "visual_value"],
    "p450": ["research", "story", "visual_value", "script", "manifest"],
    "p570": ["research", "story", "visual_value", "script", "manifest", "asset"],
    "p680": ["research", "story", "visual_value", "script", "manifest", "asset", "image"],
    "p750": ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration"],
    "p850": ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration"],
    "p930": ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration", "video"],
}
for _slot in range(110, 931, 10):
    number = (_slot // 100) * 100
    if _slot < 200:
        stages = ["research"]
    elif _slot < 300:
        stages = ["research", "story"]
    elif _slot < 400:
        stages = ["research", "story", "visual_value"]
    elif _slot < 500:
        stages = ["research", "story", "visual_value", "script", "manifest"]
    elif _slot < 600:
        stages = ["research", "story", "visual_value", "script", "manifest", "asset"]
    elif _slot < 700:
        stages = ["research", "story", "visual_value", "script", "manifest", "asset", "image"]
    elif _slot < 900:
        stages = ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration"]
    else:
        stages = ["research", "story", "visual_value", "script", "manifest", "asset", "image", "narration", "video"]
    STAGE_TARGETS.setdefault(f"p{_slot}", stages)

for _target, _enabled_stages in STAGE_TARGETS.items():
    if int(_target[1:]) >= 860 and "sound_design" not in _enabled_stages:
        _enabled_stages.append("sound_design")

STAGE_TARGET_ALIASES = {
    "100": "p130", "p100": "p130", "research": "p130",
    "200": "p230", "p200": "p230", "story": "p230",
    "300": "p330", "p300": "p330", "visual": "p330", "visual_value": "p330",
    "400": "p450", "p400": "p450", "450": "p450", "script": "p450",
    "500": "p570", "p500": "p570", "asset": "p570",
    "600": "p680", "p600": "p680", "image": "p680", "image_generation": "p680", "scene_implementation": "p680",
    "700": "p750", "p700": "p750", "narration": "p750",
    "800": "p860", "p800": "p860", "video_generation": "p860", "sound_design": "p860",
    "900": "p930", "p900": "p930", "render": "p930", "video": "p930", "done": "p930",
}


def normalize_stage_target(value: str | None) -> str:
    normalized = (value or "p930").strip().lower()
    if normalized.isdigit():
        normalized = f"p{normalized}"
    if normalized in STAGE_TARGET_ALIASES:
        return STAGE_TARGET_ALIASES[normalized]
    if normalized in STAGE_TARGETS:
        return normalized
    raise ValueError(f"Unsupported stage target: {value}")


def build_report(run_dir: Path, flow: str, profile: str, stage_target: str = "p900") -> tuple[dict[str, Any], dict[str, str]]:
    state_path = run_dir / "state.txt"
    if not state_path.exists():
        append_state_snapshot(state_path, {"topic": run_dir.name, "status": "INIT", "runtime.stage": "verify"})
    target = normalize_stage_target(stage_target)
    enabled = set(STAGE_TARGETS[target])
    stages: list[dict[str, Any]] = []
    if flow != "scene-series":
        stages.append(check_orchestration(run_dir, stage_target=target)[0])
    if "research" in enabled:
        stages.append(pipeline_policy.check_research(run_dir, profile)[0])
    if "story" in enabled:
        stages.append(pipeline_policy.check_story(run_dir, profile)[0])
    if "visual_value" in enabled:
        stages.append(check_visual_value(run_dir, profile, forbid_production_artifacts=target.startswith("p3"))[0])
    if "script" in enabled:
        stages.append((pipeline_policy.check_script_scene_series(run_dir, profile) if flow == "scene-series" else pipeline_policy.check_script_single(run_dir, profile))[0])
    if "manifest" in enabled:
        stages.append((pipeline_policy.check_manifest_scene_series(run_dir, profile) if flow == "scene-series" else shared_check_manifest_single(run_dir, profile, flow))[0])
    if "asset" in enabled:
        stages.append(check_asset(run_dir, target_slot=target)[0])
    if "image" in enabled:
        stages.append(check_image(run_dir, target_slot=target)[0])
    if "narration" in enabled:
        stages.append(check_narration(run_dir)[0])
    if "video" in enabled:
        stages.append((check_video_scene_series(run_dir, target_slot=target) if flow == "scene-series" else check_video_single(run_dir, target_slot=target))[0])
    if "sound_design" in enabled:
        from server.sound_design_api import freeze as freeze_sound
        checks = []
        from server.image_gen_app import _read_manifest_data
        sound_runs = sorted(path for path in (run_dir / "scenes").glob("scene*") if path.is_dir()) if flow == "scene-series" else [run_dir]
        add_check(checks, "sound_design.runs", bool(sound_runs), "sound design run directories exist")
        for sound_run in sound_runs:
            try:
                freeze_sound(sound_run, _read_manifest_data(sound_run)[2])
                add_check(checks, f"sound_design.current:{sound_run.name}", True, "current video approval and completed BGM/SE selections verified")
            except (ValueError, FileNotFoundError) as exc:
                add_check(checks, f"sound_design.current:{sound_run.name}", False, str(exc))
        stages.append(pipeline_policy.make_stage("sound_design", "sound_design.json", checks))
    report = {
        "generated_at": now_iso(),
        "run_dir": str(run_dir.resolve()),
        "flow": flow,
        "profile": profile,
        "stage_target": target,
        "overall": {
            "passed": all(stage.get("passed") is True for stage in stages),
            "failed_stages": [stage["stage"] for stage in stages if stage.get("passed") is not True],
        },
        "stages": {stage["stage"]: stage for stage in stages},
    }
    return report, {}


def render_run_report(report: dict[str, Any], state: dict[str, str], run_dir: Path) -> str:
    del state
    overall = report["overall"]
    lines = [
        "# Verification Report",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Flow: `{report['flow']}`",
        f"- Profile: `{report['profile']}`",
        f"- Stage target: `{report.get('stage_target', 'p930')}`",
        f"- Overall: `{'PASS' if overall['passed'] else 'FAIL'}`",
        f"- Run dir: `{run_dir}`",
        "",
        "## Stage Summary",
        "",
        "| Stage | Result |",
        "| --- | --- |",
    ]
    stage_order = ["orchestration", "research", "story", "visual_value", "script", "manifest", "asset", "image", "narration", "video"]
    for name in stage_order:
        stage = report["stages"].get(name)
        if stage:
            lines.append(f"| {name} | {'PASS' if stage.get('passed') else 'FAIL'} |")
    lines += ["", "## Checks", ""]
    for name in stage_order:
        stage = report["stages"].get(name)
        if not stage:
            continue
        lines.append(f"### {name}")
        for check in stage.get("checks", []):
            lines.append(f"- [{'PASS' if check.get('passed') else 'FAIL'}] `{check.get('id')}`: {check.get('message')}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify ToC run artifacts and write a structural report.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--flow", required=True, choices=["toc-run", "scene-series", "immersive"])
    parser.add_argument("--profile", default="standard", choices=["fast", "standard"])
    parser.add_argument("--stage-target", "--p-slot", default="p900")
    args = parser.parse_args()
    run_dir = Path(args.run_dir)
    try:
        target = normalize_stage_target(args.stage_target)
    except ValueError as exc:
        parser.error(str(exc))
    report, updates = build_report(run_dir, args.flow, args.profile, target)
    report_path = eval_report_path(run_dir)
    write_json(report_path, report)
    if updates:
        append_state_snapshot(run_dir / "state.txt", updates)
    state = parse_state_file(run_dir / "state.txt")
    run_report = run_report_path(run_dir)
    run_report.write_text(render_run_report(report, state, run_dir), encoding="utf-8")
    sync_run_status(run_dir)
    print(run_report)
    print(report_path)
    return 0 if report["overall"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
