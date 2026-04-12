"""Stage grounding contracts, readsets, and audit helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from toc.harness import append_state_snapshot, now_iso, parse_state_file, safe_load_yaml, write_json


REPO_ROOT = Path(__file__).resolve().parents[1]
GROUNDING_CONTRACT_PATH = REPO_ROOT / "workflow" / "stage-grounding.yaml"
APPROVAL_POLICY_DEFAULTS: dict[str, str] = {
    "story": "required",
    "image": "required",
    "narration": "required",
}
APPROVAL_POLICY_PRESETS: dict[str, dict[str, str]] = {
    "strict": dict(APPROVAL_POLICY_DEFAULTS),
    "drafts": {
        "story": "optional",
        "image": "optional",
        "narration": "optional",
    },
}


class StageGroundingError(RuntimeError):
    def __init__(self, *, stage: str, status: str, run_dir: Path, report: dict[str, Any]) -> None:
        self.stage = stage
        self.status = status
        self.run_dir = run_dir
        self.report = report
        super().__init__(self._message())

    def _message(self) -> str:
        missing = ", ".join(str(entry.get("path") or "") for entry in self.report.get("missing_paths", [])) or "none"
        return f"Grounding failed for stage={self.stage} status={self.status} run_dir={self.run_dir} missing={missing}"


class StagePlaybookSelectionError(RuntimeError):
    def __init__(
        self,
        *,
        stage: str,
        run_dir: Path,
        invalid_paths: list[str],
        available_paths: list[str],
    ) -> None:
        self.stage = stage
        self.run_dir = run_dir
        self.invalid_paths = invalid_paths
        self.available_paths = available_paths
        super().__init__(self._message())

    def _message(self) -> str:
        invalid = ", ".join(self.invalid_paths) or "none"
        available = ", ".join(self.available_paths) or "none"
        return f"Playbook selection failed for stage={self.stage} run_dir={self.run_dir} invalid={invalid} available={available}"


def normalize_review_policy_value(value: str | None, *, default: str = "required") -> str:
    raw = str(value or "").strip().lower()
    if raw in {"required", "optional"}:
        return raw
    return default


def resolve_review_policy(
    *,
    preset: str = "strict",
    story_review: str | None = None,
    image_review: str | None = None,
    narration_review: str | None = None,
) -> dict[str, str]:
    base = dict(APPROVAL_POLICY_PRESETS.get(preset, APPROVAL_POLICY_PRESETS["strict"]))
    overrides = {
        "story": story_review,
        "image": image_review,
        "narration": narration_review,
    }
    for key, raw in overrides.items():
        if raw is None:
            continue
        base[key] = normalize_review_policy_value(raw, default=base.get(key, "required"))
    return base


def review_policy_state_entries(policy: dict[str, str]) -> dict[str, str]:
    normalized = {key: normalize_review_policy_value(policy.get(key), default=value) for key, value in APPROVAL_POLICY_DEFAULTS.items()}
    return {
        "review.policy.story": normalized["story"],
        "review.policy.image": normalized["image"],
        "review.policy.narration": normalized["narration"],
        "gate.story_review": normalized["story"],
        "gate.image_review": normalized["image"],
        "gate.narration_review": normalized["narration"],
    }


def current_review_policy(state: dict[str, str]) -> dict[str, str]:
    policy: dict[str, str] = {}
    for key, default in APPROVAL_POLICY_DEFAULTS.items():
        policy[key] = normalize_review_policy_value(state.get(f"review.policy.{key}"), default=default)
    return policy


def detect_flow(run_dir: Path) -> str:
    if (run_dir / "scenes").exists():
        return "scene-series"
    manifest_path = run_dir / "video_manifest.md"
    if manifest_path.exists():
        text = manifest_path.read_text(encoding="utf-8")
        if "experience:" in text:
            return "immersive"
    return "toc-run"


def parent_run_dir(run_dir: Path, flow: str | None = None) -> Path | None:
    resolved_flow = flow or detect_flow(run_dir)
    if resolved_flow != "scene-series":
        return None
    if run_dir.parent.name != "scenes":
        return None
    return run_dir.parent.parent


def load_grounding_contract(path: Path = GROUNDING_CONTRACT_PATH) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Grounding contract not found: {path}")
    data = safe_load_yaml(path.read_text(encoding="utf-8"))
    if not data:
        raise ValueError(f"Failed to parse grounding contract: {path}")
    return data


def _load_mapping_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    data = safe_load_yaml(text)
    if isinstance(data, dict) and data:
        return data
    try:
        payload = json.loads(text)
    except Exception:
        return None
    return payload if isinstance(payload, dict) and payload else None


def canonical_stage_name(stage: str, contract: dict[str, Any] | None = None) -> str:
    loaded = contract or load_grounding_contract()
    aliases = loaded.get("aliases") if isinstance(loaded.get("aliases"), dict) else {}
    return str(aliases.get(stage, stage))


def stage_name_candidates(stage: str, contract: dict[str, Any] | None = None) -> list[str]:
    loaded = contract or load_grounding_contract()
    aliases = loaded.get("aliases") if isinstance(loaded.get("aliases"), dict) else {}
    canonical = canonical_stage_name(stage, loaded)

    out: list[str] = []
    for candidate in [stage, canonical]:
        if candidate not in out:
            out.append(candidate)
    for alias, resolved in aliases.items():
        if resolved == canonical and alias not in out:
            out.append(str(alias))
    return out


def stage_contract(stage: str, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    loaded = contract or load_grounding_contract()
    stages = loaded.get("stages") if isinstance(loaded.get("stages"), dict) else {}
    canonical = canonical_stage_name(stage, loaded)
    value = stages.get(canonical)
    if not isinstance(value, dict):
        raise KeyError(f"Stage grounding contract not found: {stage}")
    return value


def global_required_docs(contract: dict[str, Any] | None = None) -> list[str]:
    loaded = contract or load_grounding_contract()
    value = loaded.get("global_required_docs")
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def grounding_report_relpath(stage: str) -> Path:
    return Path("logs") / "grounding" / f"{stage}.json"


def grounding_report_path(run_dir: Path, stage: str) -> Path:
    return run_dir / grounding_report_relpath(stage)


def load_grounding_report(run_dir: Path, stage: str, contract: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, Path | None]:
    loaded = contract or load_grounding_contract()
    for candidate in stage_name_candidates(stage, loaded):
        path = grounding_report_path(run_dir, candidate)
        if not path.exists():
            continue
        data = _load_mapping_file(path)
        if isinstance(data, dict) and data:
            return data, path
    return None, None


def state_grounding_key_candidates(stage: str, contract: dict[str, Any] | None = None) -> list[str]:
    return [f"stage.{candidate}.grounding.status" for candidate in stage_name_candidates(stage, contract)]


def state_grounding_report_key_candidates(stage: str, contract: dict[str, Any] | None = None) -> list[str]:
    return [f"stage.{candidate}.grounding.report" for candidate in stage_name_candidates(stage, contract)]


def grounding_readset_relpath(stage: str) -> Path:
    return Path("logs") / "grounding" / f"{stage}.readset.json"


def grounding_readset_path(run_dir: Path, stage: str) -> Path:
    return run_dir / grounding_readset_relpath(stage)


def load_grounding_readset(run_dir: Path, stage: str, contract: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, Path | None]:
    loaded = contract or load_grounding_contract()
    for candidate in stage_name_candidates(stage, loaded):
        path = grounding_readset_path(run_dir, candidate)
        data = _load_mapping_file(path)
        if isinstance(data, dict) and data:
            return data, path
    return None, None


def state_readset_report_key_candidates(stage: str, contract: dict[str, Any] | None = None) -> list[str]:
    return [f"stage.{candidate}.readset.report" for candidate in stage_name_candidates(stage, contract)]


def grounding_audit_relpath(stage: str) -> Path:
    return Path("logs") / "grounding" / f"{stage}.audit.json"


def grounding_audit_path(run_dir: Path, stage: str) -> Path:
    return run_dir / grounding_audit_relpath(stage)


def load_grounding_audit(run_dir: Path, stage: str, contract: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, Path | None]:
    loaded = contract or load_grounding_contract()
    for candidate in stage_name_candidates(stage, loaded):
        path = grounding_audit_path(run_dir, candidate)
        data = _load_mapping_file(path)
        if isinstance(data, dict) and data:
            return data, path
    return None, None


def state_audit_status_key_candidates(stage: str, contract: dict[str, Any] | None = None) -> list[str]:
    return [f"stage.{candidate}.audit.status" for candidate in stage_name_candidates(stage, contract)]


def state_audit_report_key_candidates(stage: str, contract: dict[str, Any] | None = None) -> list[str]:
    return [f"stage.{candidate}.audit.report" for candidate in stage_name_candidates(stage, contract)]


def playbooks_report_relpath(stage: str) -> Path:
    return Path("logs") / "grounding" / f"{stage}.playbooks.json"


def playbooks_report_path(run_dir: Path, stage: str) -> Path:
    return run_dir / playbooks_report_relpath(stage)


def load_playbooks_report(run_dir: Path, stage: str, contract: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, Path | None]:
    loaded = contract or load_grounding_contract()
    for candidate in stage_name_candidates(stage, loaded):
        path = playbooks_report_path(run_dir, candidate)
        data = _load_mapping_file(path)
        if isinstance(data, dict) and data:
            return data, path
    return None, None


def state_playbooks_report_key_candidates(stage: str, contract: dict[str, Any] | None = None) -> list[str]:
    return [f"stage.{candidate}.playbooks.report" for candidate in stage_name_candidates(stage, contract)]


def state_playbooks_selected_count_key_candidates(stage: str, contract: dict[str, Any] | None = None) -> list[str]:
    return [f"stage.{candidate}.playbooks.selected_count" for candidate in stage_name_candidates(stage, contract)]


def _repo_entry(path_text: str, *, kind: str) -> dict[str, Any]:
    resolved = (REPO_ROOT / path_text).resolve()
    return {
        "kind": kind,
        "path": path_text,
        "resolved_path": str(resolved),
        "exists": resolved.exists(),
    }


def _run_entry(run_dir: Path, path_text: str, *, flow: str | None = None) -> dict[str, Any]:
    search_roots = [run_dir]
    inherited_root = parent_run_dir(run_dir, flow)
    if inherited_root is not None and inherited_root not in search_roots:
        search_roots.append(inherited_root)

    resolved = (run_dir / path_text).resolve()
    source = "run_dir"
    exists = resolved.exists()
    if not exists:
        for candidate_root in search_roots[1:]:
            candidate = (candidate_root / path_text).resolve()
            if candidate.exists():
                resolved = candidate
                exists = True
                source = "parent_run_dir"
                break

    return {
        "kind": "input",
        "path": path_text,
        "resolved_path": str(resolved),
        "exists": exists,
        "source": source,
    }


def _load_state_for_grounding(run_dir: Path, *, flow: str | None = None) -> dict[str, str]:
    inherited_root = parent_run_dir(run_dir, flow)
    merged: dict[str, str] = {}
    if inherited_root is not None:
        merged.update(parse_state_file(inherited_root / "state.txt"))
    merged.update(parse_state_file(run_dir / "state.txt"))
    return merged


def resolve_stage_grounding(*, stage: str, run_dir: Path, flow: str | None = None, contract_path: Path = GROUNDING_CONTRACT_PATH) -> dict[str, Any]:
    contract = load_grounding_contract(contract_path)
    stage_spec = stage_contract(stage, contract)
    resolved_flow = flow or detect_flow(run_dir)

    required_global_docs = [_repo_entry(path, kind="global_doc") for path in global_required_docs(contract)]
    required_docs = [_repo_entry(path, kind="doc") for path in stage_spec.get("required_docs", []) if isinstance(path, str)]
    required_templates = [_repo_entry(path, kind="template") for path in stage_spec.get("required_templates", []) if isinstance(path, str)]
    required_inputs = [_run_entry(run_dir, path, flow=resolved_flow) for path in stage_spec.get("required_inputs", []) if isinstance(path, str)]
    optional_playbooks = [_repo_entry(path, kind="playbook") for path in stage_spec.get("optional_playbooks", []) if isinstance(path, str)]

    state = _load_state_for_grounding(run_dir, flow=resolved_flow)
    approved_input_checks: list[dict[str, Any]] = []
    approved_ok = True
    for raw in stage_spec.get("requires_approved_input", []):
        if not isinstance(raw, dict):
            continue
        path_text = str(raw.get("path") or "").strip()
        review_key = str(raw.get("review_key") or "").strip()
        allowed_values = [str(value).strip().lower() for value in raw.get("allowed_values", []) if str(value).strip()]
        policy_key = str(raw.get("policy_key") or "").strip()
        required_when = [str(value).strip().lower() for value in raw.get("required_when", []) if str(value).strip()]
        path_entry = _run_entry(run_dir, path_text, flow=resolved_flow) if path_text else {"exists": False, "resolved_path": "", "source": "run_dir"}
        exists = bool(path_text) and bool(path_entry["exists"])
        review_value = str(state.get(review_key, "")).strip().lower()
        policy_default = "required" if policy_key else ""
        policy_value = normalize_review_policy_value(state.get(policy_key), default=policy_default) if policy_key else ""
        approval_required = (not policy_key) or (policy_value in set(required_when or ["required"]))
        passed = exists and (not approval_required or (bool(review_key) and review_value in set(allowed_values)))
        if not passed:
            approved_ok = False
        approved_input_checks.append(
            {
                "path": path_text,
                "resolved_path": str(path_entry.get("resolved_path") or ""),
                "source": str(path_entry.get("source") or "run_dir"),
                "exists": exists,
                "review_key": review_key,
                "review_value": review_value,
                "allowed_values": allowed_values,
                "policy_key": policy_key,
                "policy_value": policy_value,
                "required_when": required_when,
                "approval_required": approval_required,
                "passed": passed,
            }
        )

    missing_paths = [entry for entry in [*required_global_docs, *required_docs, *required_templates, *required_inputs] if not entry["exists"]]
    missing_docs = any(entry["kind"] in {"global_doc", "doc", "template"} for entry in missing_paths)
    missing_inputs = any(entry["kind"] == "input" for entry in missing_paths) or not approved_ok
    if missing_docs:
        status = "missing_docs"
    elif missing_inputs:
        status = "missing_inputs"
    else:
        status = "ready"

    return {
        "generated_at": now_iso(),
        "contract_version": contract.get("contract_version"),
        "stage": stage,
        "canonical_stage": canonical_stage_name(stage, contract),
        "flow": resolved_flow,
        "run_dir": str(run_dir.resolve()),
        "parent_run_dir": str(parent_run_dir(run_dir, resolved_flow).resolve()) if parent_run_dir(run_dir, resolved_flow) else "",
        "required_paths": {
            "global_docs": [entry["path"] for entry in required_global_docs],
            "docs": [entry["path"] for entry in required_docs],
            "templates": [entry["path"] for entry in required_templates],
            "inputs": [entry["path"] for entry in required_inputs],
        },
        "resolved_paths": {
            "global_docs": required_global_docs,
            "docs": required_docs,
            "templates": required_templates,
            "inputs": required_inputs,
            "optional_playbooks": optional_playbooks,
        },
        "missing_paths": missing_paths,
        "approved_input_checks": approved_input_checks,
        "status": status,
        "review_policy": current_review_policy(state),
    }


def select_stage_playbooks(
    *,
    stage: str,
    run_dir: Path,
    selected_paths: list[str] | None = None,
    select_all: bool = False,
    flow: str | None = None,
    contract_path: Path = GROUNDING_CONTRACT_PATH,
) -> dict[str, Any]:
    contract = load_grounding_contract(contract_path)
    stage_spec = stage_contract(stage, contract)
    resolved_flow = flow or detect_flow(run_dir)
    available = [_repo_entry(path, kind="playbook") for path in stage_spec.get("optional_playbooks", []) if isinstance(path, str)]
    available_paths = [str(entry["path"]) for entry in available]
    available_map = {entry["path"]: entry for entry in available}

    if select_all:
        normalized_selected = list(available_paths)
        selection_mode = "all"
    else:
        normalized_selected = []
        seen: set[str] = set()
        for raw in selected_paths or []:
            candidate = str(raw or "").strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized_selected.append(candidate)
        selection_mode = "explicit" if normalized_selected else "none"

    invalid_paths = [path for path in normalized_selected if path not in available_map]
    if invalid_paths:
        raise StagePlaybookSelectionError(
            stage=stage,
            run_dir=run_dir,
            invalid_paths=invalid_paths,
            available_paths=available_paths,
        )

    report = {
        "generated_at": now_iso(),
        "contract_version": contract.get("contract_version"),
        "stage": stage,
        "canonical_stage": canonical_stage_name(stage, contract),
        "flow": resolved_flow,
        "run_dir": str(run_dir.resolve()),
        "grounding_report": str(grounding_report_relpath(stage)),
        "selection_mode": selection_mode,
        "available_optional_playbooks": available,
        "selected_optional_playbooks": [available_map[path] for path in normalized_selected],
        "selected_paths": normalized_selected,
        "selected_count": len(normalized_selected),
    }
    write_json(playbooks_report_path(run_dir, stage), report)
    append_state_snapshot(
        run_dir / "state.txt",
        {
            f"stage.{stage}.playbooks.report": str(playbooks_report_relpath(stage)),
            f"stage.{stage}.playbooks.selected_count": str(len(normalized_selected)),
        },
    )
    return report


def write_stage_grounding_report(*, run_dir: Path, stage: str, report: dict[str, Any]) -> Path:
    path = grounding_report_path(run_dir, stage)
    write_json(path, report)
    return path


def build_stage_grounding_readset(report: dict[str, Any], *, stage: str) -> dict[str, Any]:
    return {
        "generated_at": now_iso(),
        "contract_version": report.get("contract_version"),
        "stage": stage,
        "canonical_stage": report.get("canonical_stage"),
        "flow": report.get("flow"),
        "run_dir": report.get("run_dir"),
        "grounding_report": str(grounding_report_relpath(stage)),
        "verified_before_edit": bool(report.get("status") == "ready"),
        "global_docs": list(report.get("resolved_paths", {}).get("global_docs", [])),
        "stage_docs": list(report.get("resolved_paths", {}).get("docs", [])),
        "templates": list(report.get("resolved_paths", {}).get("templates", [])),
        "inputs": list(report.get("resolved_paths", {}).get("inputs", [])),
        "optional_playbooks": list(report.get("resolved_paths", {}).get("optional_playbooks", [])),
        "review_policy": dict(report.get("review_policy", {})),
        "read_order": ["global_docs", "stage_docs", "templates", "inputs"],
    }


def write_stage_grounding_readset(*, run_dir: Path, stage: str, readset: dict[str, Any]) -> Path:
    path = grounding_readset_path(run_dir, stage)
    write_json(path, readset)
    return path


def build_stage_grounding_audit(
    *,
    run_dir: Path,
    stage: str,
    report: dict[str, Any],
    readset: dict[str, Any],
    contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    loaded = contract or load_grounding_contract()
    expected_global = set(global_required_docs(loaded))
    readset_global = {str(entry.get("path") or "").strip() for entry in readset.get("global_docs", []) if str(entry.get("path") or "").strip()}
    expected_stage_docs = {str(entry.get("path") or "").strip() for entry in report.get("resolved_paths", {}).get("docs", []) if str(entry.get("path") or "").strip()}
    readset_stage_docs = {str(entry.get("path") or "").strip() for entry in readset.get("stage_docs", []) if str(entry.get("path") or "").strip()}

    missing_global = sorted(expected_global - readset_global)
    missing_stage_docs = sorted(expected_stage_docs - readset_stage_docs)
    readset_global_exists = all(bool(entry.get("exists")) for entry in readset.get("global_docs", []))
    readset_stage_docs_exist = all(bool(entry.get("exists")) for entry in readset.get("stage_docs", []))
    readset_verified = bool(readset.get("verified_before_edit"))

    checks = [
        {"id": f"{stage}.audit.grounding_ready", "passed": report.get("status") == "ready", "message": f"grounding status is ready (got {report.get('status', '(unset)')})"},
        {"id": f"{stage}.audit.readset_verified", "passed": readset_verified, "message": "readset is marked verified_before_edit"},
        {"id": f"{stage}.audit.global_docs_present", "passed": not missing_global, "message": f"global docs are included in readset (missing {missing_global or 'none'})"},
        {"id": f"{stage}.audit.global_docs_exist", "passed": readset_global_exists, "message": "global docs in readset all resolve to existing files"},
        {"id": f"{stage}.audit.stage_docs_present", "passed": not missing_stage_docs, "message": f"stage docs are included in readset (missing {missing_stage_docs or 'none'})"},
        {"id": f"{stage}.audit.stage_docs_exist", "passed": readset_stage_docs_exist, "message": "stage docs in readset all resolve to existing files"},
    ]
    status = "passed" if all(check["passed"] for check in checks) else "failed"
    return {
        "generated_at": now_iso(),
        "stage": stage,
        "canonical_stage": report.get("canonical_stage"),
        "flow": report.get("flow"),
        "run_dir": str(run_dir.resolve()),
        "grounding_report": str(grounding_report_relpath(stage)),
        "readset_report": str(grounding_readset_relpath(stage)),
        "status": status,
        "checks": checks,
        "missing_global_docs": missing_global,
        "missing_stage_docs": missing_stage_docs,
    }


def write_stage_grounding_audit(*, run_dir: Path, stage: str, audit: dict[str, Any]) -> Path:
    path = grounding_audit_path(run_dir, stage)
    write_json(path, audit)
    return path


def grounding_validation(run_dir: Path, stage: str, contract: dict[str, Any] | None = None) -> dict[str, Any]:
    loaded = contract or load_grounding_contract()
    report, path = load_grounding_report(run_dir, stage, loaded)
    readset, readset_path = load_grounding_readset(run_dir, stage, loaded)
    audit, audit_path = load_grounding_audit(run_dir, stage, loaded)
    playbooks, playbooks_path = load_playbooks_report(run_dir, stage, loaded)
    report_flow = str((report or {}).get("flow") or "")
    state = _load_state_for_grounding(run_dir, flow=report_flow or None)

    status_key = None
    for candidate in state_grounding_key_candidates(stage, loaded):
        if candidate in state:
            status_key = candidate
            break
    report_key = None
    for candidate in state_grounding_report_key_candidates(stage, loaded):
        if candidate in state:
            report_key = candidate
            break
    readset_key = None
    for candidate in state_readset_report_key_candidates(stage, loaded):
        if candidate in state:
            readset_key = candidate
            break
    audit_status_key = None
    for candidate in state_audit_status_key_candidates(stage, loaded):
        if candidate in state:
            audit_status_key = candidate
            break
    audit_report_key = None
    for candidate in state_audit_report_key_candidates(stage, loaded):
        if candidate in state:
            audit_report_key = candidate
            break
    playbooks_report_key = None
    for candidate in state_playbooks_report_key_candidates(stage, loaded):
        if candidate in state:
            playbooks_report_key = candidate
            break
    playbooks_selected_count_key = None
    for candidate in state_playbooks_selected_count_key_candidates(stage, loaded):
        if candidate in state:
            playbooks_selected_count_key = candidate
            break

    return {
        "report": report,
        "report_path": path,
        "report_exists": report is not None and path is not None,
        "report_ready": bool(report and report.get("status") == "ready"),
        "readset": readset,
        "readset_path": readset_path,
        "readset_exists": readset is not None and readset_path is not None,
        "audit": audit,
        "audit_path": audit_path,
        "audit_exists": audit is not None and audit_path is not None,
        "audit_passed": bool(audit and audit.get("status") == "passed"),
        "state_status_key": status_key,
        "state_status": state.get(status_key, "").strip() if status_key else "",
        "state_report_key": report_key,
        "state_report": state.get(report_key, "").strip() if report_key else "",
        "state_readset_key": readset_key,
        "state_readset": state.get(readset_key, "").strip() if readset_key else "",
        "state_audit_status_key": audit_status_key,
        "state_audit_status": state.get(audit_status_key, "").strip() if audit_status_key else "",
        "state_audit_report_key": audit_report_key,
        "state_audit_report": state.get(audit_report_key, "").strip() if audit_report_key else "",
        "playbooks": playbooks,
        "playbooks_path": playbooks_path,
        "playbooks_exists": playbooks is not None and playbooks_path is not None,
        "playbooks_selected_count": int(playbooks.get("selected_count", 0)) if isinstance(playbooks, dict) else 0,
        "state_playbooks_report_key": playbooks_report_key,
        "state_playbooks_report": state.get(playbooks_report_key, "").strip() if playbooks_report_key else "",
        "state_playbooks_selected_count_key": playbooks_selected_count_key,
        "state_playbooks_selected_count": state.get(playbooks_selected_count_key, "").strip() if playbooks_selected_count_key else "",
    }


def run_stage_grounding(
    run_dir: Path,
    stage: str,
    *,
    flow: str | None = None,
    retries: int = 1,
    mark_stage_failure: bool = True,
) -> dict[str, Any]:
    attempts = max(0, int(retries)) + 1
    last_report: dict[str, Any] | None = None
    contract = load_grounding_contract()

    for _ in range(attempts):
        report = resolve_stage_grounding(stage=stage, run_dir=run_dir, flow=flow)
        report_path = write_stage_grounding_report(run_dir=run_dir, stage=stage, report=report)
        readset = build_stage_grounding_readset(report, stage=stage)
        readset_path = write_stage_grounding_readset(run_dir=run_dir, stage=stage, readset=readset)
        audit = build_stage_grounding_audit(run_dir=run_dir, stage=stage, report=report, readset=readset, contract=contract)
        audit_path = write_stage_grounding_audit(run_dir=run_dir, stage=stage, audit=audit)
        append_state_snapshot(
            run_dir / "state.txt",
            {
                f"stage.{stage}.grounding.status": str(report["status"]),
                f"stage.{stage}.grounding.report": str(report_path.relative_to(run_dir)),
                f"stage.{stage}.readset.report": str(readset_path.relative_to(run_dir)),
                f"stage.{stage}.audit.status": str(audit["status"]),
                f"stage.{stage}.audit.report": str(audit_path.relative_to(run_dir)),
            },
        )
        last_report = report
        if report["status"] == "ready" and audit["status"] == "passed":
            return report

    assert last_report is not None
    if mark_stage_failure:
        append_state_snapshot(
            run_dir / "state.txt",
            {
                f"stage.{stage}.status": "failed",
                "last_error": f"grounding_failed:{stage}:{last_report['status']}",
            },
        )
    raise StageGroundingError(stage=stage, status=str(last_report["status"]), run_dir=run_dir, report=last_report)


def prepare_stage_context(
    run_dir: Path,
    stage: str,
    *,
    flow: str | None = None,
    retries: int = 0,
    mark_stage_failure: bool = False,
) -> dict[str, Any]:
    contract = load_grounding_contract()
    report = run_stage_grounding(
        run_dir,
        stage,
        flow=flow,
        retries=retries,
        mark_stage_failure=mark_stage_failure,
    )
    validation = grounding_validation(run_dir, stage, contract)
    canonical_stage = canonical_stage_name(stage, contract)
    resolved_flow = str(report.get("flow") or flow or detect_flow(run_dir))

    if not validation.get("report_ready") or not validation.get("readset_exists") or not validation.get("audit_passed"):
        raise StageGroundingError(stage=canonical_stage, status=str(report["status"]), run_dir=run_dir, report=report)

    readset = validation.get("readset") or {}
    playbooks = validation.get("playbooks") or {}
    return {
        "stage": canonical_stage,
        "flow": resolved_flow,
        "run_dir": str(run_dir.resolve()),
        "report_path": str((validation.get("report_path") or grounding_report_path(run_dir, canonical_stage)).resolve()),
        "readset_path": str((validation.get("readset_path") or grounding_readset_path(run_dir, canonical_stage)).resolve()),
        "audit_path": str((validation.get("audit_path") or grounding_audit_path(run_dir, canonical_stage)).resolve()),
        "playbooks_report_path": str((validation.get("playbooks_path") or playbooks_report_path(run_dir, canonical_stage)).resolve()) if validation.get("playbooks_path") else "",
        "read_order": list(readset.get("read_order") or []),
        "global_docs": list(readset.get("global_docs") or []),
        "stage_docs": list(readset.get("stage_docs") or []),
        "templates": list(readset.get("templates") or []),
        "inputs": list(readset.get("inputs") or []),
        "optional_playbooks": list(readset.get("optional_playbooks") or []),
        "selected_optional_playbooks": list((playbooks or {}).get("selected_optional_playbooks") or []),
        "selected_optional_playbook_paths": list((playbooks or {}).get("selected_paths") or []),
        "selected_optional_playbook_count": int((playbooks or {}).get("selected_count", 0) or 0),
        "verified_before_edit": bool(readset.get("verified_before_edit")),
    }
