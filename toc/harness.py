"""Shared harness helpers for ToC state, reports, and structured artifacts."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional import fallback
    yaml = None


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def new_job_id(now: dt.datetime | None = None) -> str:
    n = now or dt.datetime.now()
    return f"JOB_{n.strftime('%Y-%m-%d')}_{n.strftime('%H%M%S')}"


def extract_yaml_block(text: str) -> str:
    match = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not match:
        raise ValueError("No ```yaml ... ``` block found.")
    return match.group(1)


def safe_load_yaml(text: str) -> dict[str, Any]:
    if yaml is None:
        return {}
    try:
        data = yaml.safe_load(text)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_structured_document(path: Path) -> tuple[str, dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    candidates = [text]
    try:
        candidates.insert(0, extract_yaml_block(text))
    except ValueError:
        pass

    for candidate in candidates:
        data = safe_load_yaml(candidate)
        if data:
            return text, data
    return text, {}


def parse_state_file(state_path: Path) -> dict[str, str]:
    if not state_path.exists():
        return {}
    merged: dict[str, str] = {}
    for raw in state_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().replace("\n", " ")
        if key:
            merged[key] = value
    return merged


def _order_keys(state: dict[str, str]) -> list[str]:
    preferred = [
        "timestamp",
        "job_id",
        "topic",
        "status",
        "runtime.stage",
        "runtime.render.status",
        "immersive.experience",
        "gate.research_review",
        "gate.story_review",
        "gate.image_prompt_review",
        "gate.narration_review",
        "gate.video_review",
        "gate.hybridization_review",
        "review.hybridization.status",
        "review.hybridization.at",
        "review.hybridization.note",
        "review.image_prompt.status",
        "review.image_prompt.at",
        "review.image_prompt.note",
        "review.narration.status",
        "review.narration.at",
        "review.narration.note",
        "review.video.status",
        "review.video.at",
        "review.video.note",
        "eval.image_prompt.score",
        "eval.image_prompt.findings",
        "eval.image_prompt.unresolved_entries",
        "eval.narration.score",
        "eval.narration.findings",
        "eval.narration.unresolved_entries",
        "eval.research.status",
        "eval.research.score",
        "eval.research.findings",
        "eval.story.score",
        "eval.script.status",
        "eval.script.score",
        "eval.script.findings",
        "eval.manifest.status",
        "eval.manifest.score",
        "eval.manifest.findings",
        "eval.video.status",
        "eval.video.score",
        "eval.video.findings",
        "selection.story.candidate_count",
        "selection.story.chosen_id",
        "artifact.research",
        "artifact.research_review",
        "artifact.story",
        "artifact.script",
        "artifact.script_review",
        "artifact.video_manifest",
        "artifact.manifest_review",
        "artifact.eval_report",
        "artifact.video",
        "artifact.video_review_report",
        "artifact.video.short.01",
        "last_error",
    ]
    out = [key for key in preferred if key in state]
    out.extend(sorted(key for key in state if key not in set(preferred)))
    return out


def _nested_set(target: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    cur = target
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def nested_state(flat_state: dict[str, str]) -> dict[str, Any]:
    nested: dict[str, Any] = {}
    for key, value in flat_state.items():
        _nested_set(nested, key, value)
    return nested


def resolve_artifact_path(run_dir: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else (run_dir / path)


def artifact_inventory(run_dir: Path, state: dict[str, str]) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for key, value in state.items():
        if not key.startswith("artifact."):
            continue
        artifact_name = key.removeprefix("artifact.")
        resolved = resolve_artifact_path(run_dir, value)
        inventory[artifact_name] = {
            "path": str(resolved if resolved is not None else value),
            "exists": bool(resolved and resolved.exists()),
        }
    return inventory


def pending_gates(state: dict[str, str]) -> list[str]:
    pending: list[str] = []
    gate_pairs = [
        ("research_review", "review.research.status"),
        ("story_review", "review.story.status"),
        ("image_prompt_review", "review.image_prompt.status"),
        ("narration_review", "review.narration.status"),
        ("hybridization_review", "review.hybridization.status"),
        ("video_review", "review.video.status"),
    ]
    for gate_name, review_key in gate_pairs:
        gate_value = state.get(f"gate.{gate_name}", "").strip().lower()
        review_value = state.get(review_key, "").strip().lower()
        if gate_value != "required":
            continue
        if review_value in {"approved", "rejected", "changes_requested"}:
            continue
        pending.append(gate_name)
    return pending


def run_status_path(run_dir: Path) -> Path:
    return run_dir / "run_status.json"


def eval_report_path(run_dir: Path) -> Path:
    return run_dir / "eval_report.json"


def run_report_path(run_dir: Path) -> Path:
    return run_dir / "run_report.md"


def sync_run_status(run_dir: Path, state: dict[str, str] | None = None) -> Path:
    state_path = run_dir / "state.txt"
    merged = state or parse_state_file(state_path)
    payload = {
        "generated_at": now_iso(),
        "run_dir": str(run_dir.resolve()),
        "state_file": str(state_path.resolve()),
        "state_flat": merged,
        "state": nested_state(merged),
        "artifacts": artifact_inventory(run_dir, merged),
        "pending_gates": pending_gates(merged),
    }

    eval_path = eval_report_path(run_dir)
    if eval_path.exists():
        try:
            payload["eval_report"] = json.loads(eval_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload["eval_report"] = {"error": f"Failed to parse {eval_path.name}"}

    output_path = run_status_path(run_dir)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def append_state_snapshot(state_path: Path, updates: dict[str, str]) -> dict[str, str]:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    merged = parse_state_file(state_path)

    if "job_id" not in merged or not merged["job_id"].strip():
        merged["job_id"] = new_job_id()
    if "status" not in merged or not merged["status"].strip():
        merged["status"] = "INIT"

    cleaned = {key: value.replace("\n", " ").strip() for key, value in updates.items()}
    merged.update(cleaned)
    merged["timestamp"] = now_iso()

    lines = [f"{key}={merged[key]}" for key in _order_keys(merged)]
    block = "\n".join(lines) + "\n---\n"
    with state_path.open("a", encoding="utf-8") as handle:
        handle.write(block)

    sync_run_status(state_path.parent, merged)
    return merged


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
