from __future__ import annotations

import io
import fcntl
import hashlib
import json
import os
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from toc.image_request_snapshot import (
    ImageRequestSnapshot,
    ImageRequestSnapshotError,
    load_request_snapshot,
    materialize_request_snapshot,
    sha256_file,
    write_request_snapshot_atomic,
)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 50 * 1024 * 1024
REQUEST_FILE_BY_KIND = {
    "asset": "asset_generation_requests.md",
    "scene": "image_generation_requests.md",
}
REQUEST_SNAPSHOT_FILE_BY_KIND = {
    "asset": "asset_generation_request_snapshot.json",
    "scene": "image_generation_request_snapshot.json",
}
IMAGE_API_PROMPT_POLICY_VERSION = "image_api_prompt_v1"
IMAGE_API_PROMPT_POLICY_PREFIX = "image_api_prompt_v"
COMPILED_IMAGE_API_PROMPT_POLICY_VERSION = "image_api_prompt_v2"
FIRST_IMAGE_RETENTION_SCHEMA = "toc.first_image_retention.v1"
FIRST_IMAGE_RETENTION_RESTORE_SCHEMA = "toc.first_image_retention_restore.v1"
FIRST_IMAGE_RETENTION_RESTORE_MARKER = Path("logs/image_first_retention_restore.json")
PROMPT_SETTING_TARGETS = {
    "character": {
        "label": "キャラクター",
        "path": Path("docs/implementation/image-prompting.md"),
        "default": (
            "人物参照は assets.character_bible と image_generation.character_ids を正本にする。\n"
            "人物が出る still では、顔、髪型、衣装、年齢感、体格、シルエットを固定し、"
            "参照画像に写る同一人物として読み取れるように書く。"
        ),
    },
    "item": {
        "label": "アイテム",
        "path": Path("docs/implementation/asset-bibles.md"),
        "default": (
            "アイテムや舞台装置は assets.object_bible を正本にする。\n"
            "silhouette、材質、装飾、縮尺感、工芸の痕跡、物語上の役割を映像だけで伝える。"
        ),
    },
    "location": {
        "label": "場所",
        "path": Path("docs/implementation/asset-bibles.md"),
        "default": (
            "場所は assets.location_bible を正本にする。\n"
            "spatial identity、主要構造、光環境、場所固有の空気、参照時の見え関係を固定する。"
        ),
    },
    "scene": {
        "label": "シーン",
        "path": Path("docs/implementation/image-prompting.md"),
        "default": (
            "scene image prompt は、動画を始める最初の1フレームとして設計する。\n"
            "ただし `最初の1フレーム` / `1フレーム目` / `first frame` という制作メタ情報は prompt 本文に入れず、見えている初期状態だけを書く。\n"
            "[全体 / 不変条件]、[登場人物]、[小道具 / 舞台装置]、[シーン]、[連続性]、[禁止] の順を守る。"
        ),
    },
}


@dataclass(frozen=True)
class ImageRequestItem:
    id: str
    kind: str
    asset_type: str | None
    tool: str | None
    output: str | None
    prompt: str
    references: list[str]
    reference_count: int
    execution_lane: str
    generation_status: str | None
    existing_image: str | None
    prompt_policy_version: str | None = None
    debug_prompt_source: dict[str, Any] = field(default_factory=dict)
    prompt_sha256: str | None = None
    reference_sha256s: list[str | None] = field(default_factory=list)
    request_revision: str | None = None
    request_digest: str | None = None
    compiler_version: str | None = None
    source_digest: str | None = None
    snapshot_schema_version: str | None = None


@dataclass(frozen=True)
class ReferenceOption:
    path: str
    label: str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def output_root(root: Path | None = None) -> Path:
    return (root or repo_root()) / "output"


def sanitize_run_title(title: str) -> str:
    title = title.strip().replace(" ", "_")
    title = re.sub(r"[\\/]+", "_", title)
    title = re.sub(r"[^0-9A-Za-z_一-龠ぁ-んァ-ンー]+", "_", title)
    title = re.sub(r"_+", "_", title).strip("_")
    return title or "topic"


def reserve_run_dir(title: str, *, root: Path | None = None, timestamp: str | None = None) -> tuple[str, Path]:
    base = output_root(root)
    stamp = timestamp or time.strftime("%Y%m%d_%H%M")
    slug = sanitize_run_title(title)
    candidate_id = f"{slug}_{stamp}"
    suffix = 2
    while True:
        run_dir = base / candidate_id
        try:
            run_dir.mkdir(parents=True, exist_ok=False)
            return candidate_id, run_dir
        except FileExistsError:
            pass
        candidate_id = f"{slug}_{stamp}_{suffix}"
        suffix += 1


def safe_run_dir(run_id: str, root: Path | None = None) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    candidate = output_root(root) / run_id
    resolved = candidate.resolve()
    base = output_root(root).resolve()
    if base not in resolved.parents and resolved != base:
        raise ValueError("run_id escapes output root")
    if not resolved.is_dir():
        raise FileNotFoundError(f"run folder not found: {run_id}")
    return resolved


def list_runs(root: Path | None = None) -> list[dict[str, Any]]:
    base = output_root(root)
    runs: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    if base.exists():
        for path in sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True):
            payload = {
                "id": path.name,
                "name": path.name,
                "path": f"output/{path.name}",
                "hasAssetRequests": (path / REQUEST_FILE_BY_KIND["asset"]).exists(),
                "hasSceneRequests": (path / REQUEST_FILE_BY_KIND["scene"]).exists(),
                "archiveOnly": False,
                "restoredFromArchive": is_first_image_retention_restored_run(path),
            }
            runs.append(payload)
            by_id[path.name] = payload

    archived_by_run: dict[str, set[str]] = {}
    for retention in list_first_image_retentions(root=root):
        archived_by_run.setdefault(str(retention["runId"]), set()).add(str(retention["kind"]))
    for run_id, kinds in sorted(archived_by_run.items()):
        existing = by_id.get(run_id)
        if existing is not None:
            existing["hasAssetRequests"] = bool(existing["hasAssetRequests"] or "asset" in kinds)
            existing["hasSceneRequests"] = bool(existing["hasSceneRequests"] or "scene" in kinds)
            continue
        runs.append(
            {
                "id": run_id,
                "name": run_id,
                "path": f"output/{run_id}",
                "hasAssetRequests": "asset" in kinds,
                "hasSceneRequests": "scene" in kinds,
                "archiveOnly": True,
                "restoredFromArchive": False,
            }
        )
    return runs


def _parse_run_state_flat(run_dir: Path) -> dict[str, str]:
    path = run_dir / "state.txt"
    if not path.exists():
        return {}
    state: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line == "---" or "=" not in line:
            continue
        key, value = line.split("=", 1)
        state[key.strip()] = value.strip()
    return state


def _parse_stage_table(index_text: str) -> list[dict[str, str]]:
    match = re.search(r"## Stage Table\s*\n\n(.*?)(?:\n## |\Z)", index_text, flags=re.DOTALL)
    if not match:
        return []
    stages: list[dict[str, str]] = []
    for raw in match.group(1).splitlines():
        line = raw.strip()
        if not line.startswith("| `p") or "---" in line:
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        stages.append({"code": cells[0], "label": cells[1], "state": cells[2]})
    return stages


def _parse_slot_contract(index_text: str) -> list[dict[str, Any]]:
    match = re.search(r"## Fixed Slot Contract\s*\n\n(.*?)(?:\n## |\Z)", index_text, flags=re.DOTALL)
    if not match:
        return []
    slots: list[dict[str, Any]] = []
    for raw in match.group(1).splitlines():
        line = raw.strip()
        if not line.startswith("| `p") or "---" in line:
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) < 5:
            continue
        artifacts = [] if cells[4] == "-" else [part.strip().strip("`") for part in cells[4].split(",") if part.strip()]
        slots.append(
            {
                "code": cells[0],
                "stage": cells[1],
                "requirement": cells[2],
                "purpose": cells[3],
                "plannedArtifacts": artifacts,
            }
        )
    status_by_code: dict[str, str] = {}
    for match in re.finditer(r"^####\s+(p\d{3})\s+.*?\n(.*?)(?=^####\s+p\d{3}\s+|^###\s+p\d{3}\s+|\Z)", index_text, flags=re.MULTILINE | re.DOTALL):
        status_match = re.search(r"^- status:\s*`([^`]+)`", match.group(2), flags=re.MULTILINE)
        if status_match:
            status_by_code[match.group(1)] = status_match.group(1)
    for slot in slots:
        slot["state"] = status_by_code.get(slot["code"], "")
    return slots


def _stage_code_number(stage: dict[str, str] | None) -> int:
    if not stage:
        return 0
    return int(re.sub(r"\D", "", stage.get("code", "")) or "0")


def _has_missing_request_outputs(run_dir: Path, kind: str) -> bool:
    try:
        items = load_request_items(run_dir, kind)
    except Exception:
        return False
    return any(item.output and not (run_dir / item.output).exists() for item in items)


def read_run_progress(run_dir: Path) -> dict[str, Any]:
    state = _parse_run_state_flat(run_dir)
    index_path = run_dir / "p000_index.md"
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    stages = _parse_stage_table(index_text) if index_text else []
    slots = _parse_slot_contract(index_text) if index_text else []
    active_states = {"not_started", "pending", "in_progress", "blocked", "awaiting_approval", "failed"}
    current_stage = next((stage for stage in stages if stage["code"] != "p000" and stage["state"] in active_states), None)
    request_stage = None
    if not (run_dir / REQUEST_FILE_BY_KIND["asset"]).exists():
        request_stage = {"code": "p550", "label": "Asset Requests", "state": "pending"}
    elif _has_missing_request_outputs(run_dir, "asset"):
        request_stage = {"code": "p560", "label": "Asset Generation", "state": "pending"}
    elif not (run_dir / REQUEST_FILE_BY_KIND["scene"]).exists():
        request_stage = {"code": "p650", "label": "Generation Ready", "state": "pending"}
    elif _has_missing_request_outputs(run_dir, "scene"):
        request_stage = {"code": "p660", "label": "Image Generation", "state": "pending"}
    if request_stage and (
        current_stage is None
        or _stage_code_number(current_stage) > _stage_code_number(request_stage)
    ):
        current_stage = request_stage
    if current_stage is None:
        current_stage = next((stage for stage in reversed(stages) if stage["code"] != "p000" and stage["state"] == "done"), None)
    done_count = sum(1 for stage in stages if stage["code"] != "p000" and stage["state"] == "done")
    total_count = sum(1 for stage in stages if stage["code"] != "p000")
    percent = round((done_count / total_count) * 100) if total_count else 0
    if request_stage and current_stage == request_stage:
        max_stage_number = max((_stage_code_number(stage) for stage in stages), default=900) or 900
        percent = min(percent, round((_stage_code_number(request_stage) / max_stage_number) * 100))
    return {
        "topic": state.get("topic") or run_dir.name,
        "status": state.get("status") or "",
        "runtimeStage": state.get("runtime.stage") or "",
        "reviewPolicy": state.get("runtime.review_policy") or "",
        "pendingGates": [key.removeprefix("gate.") for key, value in sorted(state.items()) if key.startswith("gate.") and value == "required"],
        "currentStage": current_stage,
        "stages": stages,
        "slots": slots,
        "doneCount": done_count,
        "totalCount": total_count,
        "percent": percent,
    }


def _strip_ticks(value: str) -> str:
    value = value.strip()
    if value.startswith("`") and value.endswith("`") and len(value) >= 2:
        return value[1:-1].strip()
    return value


def _parse_metadata(section: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"references": []}
    in_references = False
    for raw in section.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            if in_references:
                in_references = False
            continue
        if stripped.startswith("- references:"):
            value = stripped.split(":", 1)[1].strip()
            if value and value not in {"[]", "`[]`"}:
                metadata["references"].append(_strip_ticks(value))
                in_references = False
            else:
                in_references = not value
            continue
        if in_references and stripped.startswith("- `"):
            # Format: - `label`: `assets/foo.png`
            match = re.search(r":\s*`([^`]+)`\s*$", stripped)
            if match:
                metadata["references"].append(match.group(1).strip())
                continue
        match = re.match(r"-\s*([a-zA-Z0-9_ -]+):\s*(.*)$", stripped)
        if in_references and match:
            in_references = False
        elif in_references and stripped.startswith("- "):
            metadata["references"].append(_strip_ticks(stripped[2:]))
            continue
        if not match:
            continue
        key = match.group(1).strip().replace("-", "_")
        value = _strip_ticks(match.group(2).strip())
        metadata[key] = value
        in_references = key == "references"
    return metadata


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


FENCED_BLOCK_RE = re.compile(r"```(?P<label>[A-Za-z0-9_-]+)?[^\n]*\n(?P<body>.*?)\n```", flags=re.DOTALL)


def _extract_fenced_blocks(section: str) -> list[tuple[str, str]]:
    return [
        ((match.group("label") or "").strip().lower(), match.group("body").strip())
        for match in FENCED_BLOCK_RE.finditer(section)
    ]


def _metadata_without_fences(section: str) -> str:
    return FENCED_BLOCK_RE.sub("", section)


def _extract_request_prompt(section: str, *, prompt_policy_version: str | None = None) -> tuple[str, str, dict[str, Any]]:
    metadata_block = _metadata_without_fences(section)
    fenced_blocks = _extract_fenced_blocks(section)
    debug_prompt_source = {
        label: body
        for label, body in fenced_blocks
        if label in {"debug_prompt_source", "review_prompt_source", "yaml", "yml"}
    }
    for label, body in fenced_blocks:
        if label == "api_prompt":
            return body, metadata_block, debug_prompt_source
    if str(prompt_policy_version or "").strip().startswith(IMAGE_API_PROMPT_POLICY_PREFIX):
        raise ValueError("api_prompt_missing_for_new_prompt_policy")
    for label, body in fenced_blocks:
        if label in {"", "text", "txt"}:
            return body, metadata_block, debug_prompt_source
    prompt_lines: list[str] = []
    metadata_lines: list[str] = []
    in_prompt = False
    for raw in section.splitlines():
        stripped = raw.strip()
        inline_match = re.match(r"-\s*prompt:\s*(.*)$", stripped)
        if inline_match:
            in_prompt = True
            value = _strip_ticks(inline_match.group(1).strip())
            if value:
                prompt_lines.append(value)
            continue
        if in_prompt:
            if re.match(r"-\s*[a-zA-Z0-9_ -]+:\s*", stripped) or stripped.startswith("## "):
                in_prompt = False
                metadata_lines.append(raw)
            elif raw.startswith("  ") or raw.startswith("\t"):
                prompt_lines.append(raw.strip())
            elif stripped:
                prompt_lines.append(stripped)
            else:
                in_prompt = False
                metadata_lines.append(raw)
            continue
        metadata_lines.append(raw)
    return "\n".join(prompt_lines).strip(), "\n".join(metadata_lines), debug_prompt_source


def parse_request_markdown(text: str, *, kind: str, run_dir: Path) -> list[ImageRequestItem]:
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", text)
    items: list[ImageRequestItem] = []
    for index in range(1, len(parts), 2):
        item_id = parts[index].strip()
        section = parts[index + 1]
        metadata = _parse_metadata(_metadata_without_fences(section))
        prompt_policy_version = str(
            metadata.get("prompt_policy_version")
            or metadata.get("api_prompt_policy_version")
            or metadata.get("policy_version")
            or ""
        ).strip() or None
        prompt, metadata_block, debug_prompt_source = _extract_request_prompt(
            section,
            prompt_policy_version=prompt_policy_version,
        )
        metadata = _parse_metadata(metadata_block)
        prompt_policy_version = str(
            metadata.get("prompt_policy_version")
            or metadata.get("api_prompt_policy_version")
            or metadata.get("policy_version")
            or prompt_policy_version
            or ""
        ).strip() or None
        references = [r for r in metadata.get("references", []) if isinstance(r, str) and r.strip()]
        reference_count = _parse_int(metadata.get("reference_count"), len(references))
        execution_lane = str(metadata.get("execution_lane") or "").strip()
        if reference_count == 0:
            execution_lane = "bootstrap_builtin"
        elif not execution_lane:
            execution_lane = "standard"
        output = str(metadata.get("output") or "").strip() or None
        existing_image = output if output and (run_dir / output).exists() else None
        items.append(
            ImageRequestItem(
                id=item_id,
                kind=kind,
                asset_type=str(metadata.get("asset_type") or "").strip() or None,
                tool=str(metadata.get("tool") or "").strip() or None,
                output=output,
                prompt=prompt,
                references=references,
                reference_count=reference_count,
                execution_lane=execution_lane,
                generation_status=str(metadata.get("generation_status") or "").strip() or None,
                existing_image=existing_image,
                prompt_policy_version=prompt_policy_version,
                debug_prompt_source=debug_prompt_source,
            )
        )
    return items


def load_request_items(run_dir: Path, kind: str) -> list[ImageRequestItem]:
    filename = REQUEST_FILE_BY_KIND.get(kind)
    if not filename:
        raise ValueError("kind must be asset or scene")
    path = run_dir / filename
    if not path.exists():
        return []
    markdown_items = parse_request_markdown(path.read_text(encoding="utf-8"), kind=kind, run_dir=run_dir)
    snapshot_filename = REQUEST_SNAPSHOT_FILE_BY_KIND[kind]
    snapshot_path = run_dir / snapshot_filename
    if not snapshot_path.exists():
        if any(
            str(item.prompt_policy_version or "").startswith(IMAGE_API_PROMPT_POLICY_PREFIX)
            and item.prompt_policy_version != IMAGE_API_PROMPT_POLICY_VERSION
            for item in markdown_items
        ):
            raise ImageRequestSnapshotError(
                f"request_snapshot_missing_for_new_prompt_policy: {snapshot_filename}"
            )
        return markdown_items
    snapshot = load_request_snapshot(snapshot_path, run_dir=run_dir, verify_references=True)
    if snapshot.kind != kind:
        raise ImageRequestSnapshotError(
            f"request snapshot kind mismatch: expected {kind}, got {snapshot.kind}"
        )
    markdown_by_id = {item.id: item for item in markdown_items}
    if len(markdown_by_id) != len(markdown_items):
        raise ImageRequestSnapshotError("request Markdown contains duplicate item ids")
    if set(markdown_by_id) != {item.item_id for item in snapshot.items}:
        raise ImageRequestSnapshotError("request snapshot item ids do not match request Markdown")
    snapshot_by_id = {item.item_id: item for item in snapshot.items}
    loaded: list[ImageRequestItem] = []
    for review_item in markdown_items:
        snapshot_item = snapshot_by_id[review_item.id]
        if review_item.prompt != snapshot_item.prompt:
            raise ImageRequestSnapshotError(
                f"request Markdown prompt does not match snapshot for {snapshot_item.item_id}"
            )
        if str(review_item.output or "") != snapshot_item.destination:
            raise ImageRequestSnapshotError(
                f"request Markdown destination does not match snapshot for {snapshot_item.item_id}"
            )
        if list(review_item.references) != [reference.path for reference in snapshot_item.references]:
            raise ImageRequestSnapshotError(
                f"request Markdown references do not match snapshot for {snapshot_item.item_id}"
            )
        if str(review_item.prompt_policy_version or "") != snapshot_item.prompt_policy_version:
            raise ImageRequestSnapshotError(
                f"request Markdown policy does not match snapshot for {snapshot_item.item_id}"
            )
        loaded.append(
            ImageRequestItem(
                id=review_item.id,
                kind=kind,
                asset_type=review_item.asset_type,
                tool=review_item.tool,
                output=snapshot_item.destination,
                prompt=snapshot_item.prompt,
                references=[reference.path for reference in snapshot_item.references],
                reference_count=len(snapshot_item.references),
                execution_lane=review_item.execution_lane,
                generation_status=review_item.generation_status,
                existing_image=review_item.existing_image,
                prompt_policy_version=snapshot_item.prompt_policy_version,
                debug_prompt_source=review_item.debug_prompt_source,
                prompt_sha256=snapshot_item.prompt_sha256,
                reference_sha256s=[reference.sha256 for reference in snapshot_item.references],
                request_revision=snapshot.request_revision,
                request_digest=snapshot_item.request_digest,
                compiler_version=snapshot_item.compiler_version,
                source_digest=snapshot_item.source_digest,
                snapshot_schema_version=snapshot.schema_version,
            )
        )
    return loaded


def prompt_setting_targets() -> dict[str, dict[str, str]]:
    return {
        key: {
            "label": str(value["label"]),
            "path": str(value["path"]),
        }
        for key, value in PROMPT_SETTING_TARGETS.items()
    }


def _prompt_setting_config(target: str) -> dict[str, Any]:
    config = PROMPT_SETTING_TARGETS.get(target)
    if not config:
        raise ValueError("target must be character, item, location, or scene")
    return config


def _setting_markers(target: str) -> tuple[str, str]:
    return (f"<!-- image-gen-setting:{target}:start -->", f"<!-- image-gen-setting:{target}:end -->")


def _ensure_setting_markers(text: str, *, target: str, default: str) -> str:
    start, end = _setting_markers(target)
    if start in text and end in text:
        return text
    separator = "" if text.endswith("\n") else "\n"
    block = f"{separator}\n{start}\n{default.strip()}\n{end}\n"
    return text + block


def _extract_marked_section(text: str, *, target: str) -> str:
    start, end = _setting_markers(target)
    pattern = re.compile(rf"{re.escape(start)}\n?(.*?)\n?{re.escape(end)}", flags=re.DOTALL)
    match = pattern.search(text)
    if not match:
        raise ValueError(f"prompt setting markers not found for {target}")
    return match.group(1).strip()


def _replace_marked_section(text: str, *, target: str, content: str) -> str:
    start, end = _setting_markers(target)
    pattern = re.compile(rf"{re.escape(start)}\n?(.*?)\n?{re.escape(end)}", flags=re.DOTALL)
    replacement = f"{start}\n{content.strip()}\n{end}"
    next_text, count = pattern.subn(lambda _match: replacement, text, count=1)
    if count != 1:
        raise ValueError(f"prompt setting markers not found for {target}")
    return next_text


def read_prompt_setting(target: str, *, root: Path | None = None) -> dict[str, str]:
    config = _prompt_setting_config(target)
    base = root or repo_root()
    rel_path = config["path"]
    path = base / rel_path
    if not path.exists():
        raise FileNotFoundError(f"prompt setting source not found: {rel_path}")
    text = path.read_text(encoding="utf-8")
    text = _ensure_setting_markers(text, target=target, default=str(config["default"]))
    return {
        "target": target,
        "label": str(config["label"]),
        "path": rel_path.as_posix(),
        "content": _extract_marked_section(text, target=target),
    }


def write_prompt_setting(target: str, content: str, *, root: Path | None = None) -> dict[str, str]:
    if not content.strip():
        raise ValueError("content must not be empty")
    config = _prompt_setting_config(target)
    base = root or repo_root()
    rel_path = config["path"]
    path = base / rel_path
    if not path.exists():
        raise FileNotFoundError(f"prompt setting source not found: {rel_path}")
    text = path.read_text(encoding="utf-8")
    text = _ensure_setting_markers(text, target=target, default=str(config["default"]))
    next_text = _replace_marked_section(text, target=target, content=content)
    path.write_text(next_text if next_text.endswith("\n") else next_text + "\n", encoding="utf-8")
    return read_prompt_setting(target, root=base)


def target_to_request_kind(target: str) -> str:
    _prompt_setting_config(target)
    return "scene" if target == "scene" else "asset"


def target_matches_item(target: str, item: ImageRequestItem) -> bool:
    if target == "scene":
        return item.kind == "scene"
    asset_type = (item.asset_type or "").lower()
    output = (item.output or "").lower()
    if target == "character":
        return "character" in asset_type or output.startswith("assets/characters/")
    if target == "item":
        return "object" in asset_type or output.startswith("assets/objects/")
    if target == "location":
        return "location" in asset_type or output.startswith("assets/locations/") or output.startswith("assets/location/")
    raise ValueError("target must be character, item, location, or scene")


def update_request_prompts(run_dir: Path, kind: str, prompts_by_id: dict[str, str], *, allow_inline_prompt: bool = False) -> dict[str, list[str]]:
    filename = REQUEST_FILE_BY_KIND.get(kind)
    if not filename:
        raise ValueError("kind must be asset or scene")
    path = run_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"request file not found: {filename}")
    text = path.read_text(encoding="utf-8")
    missing: list[str] = []
    compiled_v2_items: list[str] = []
    for item_id in prompts_by_id:
        section_match = re.search(rf"(?m)^##\s+{re.escape(item_id)}\s*$", text)
        if not section_match:
            missing.append(item_id)
            break
        next_heading = re.search(r"(?m)^##\s+", text[section_match.end() :])
        section_end = section_match.end() + next_heading.start() if next_heading else len(text)
        section = text[section_match.start() : section_end]
        metadata = _parse_metadata(_metadata_without_fences(section))
        prompt_policy_version = str(
            metadata.get("prompt_policy_version")
            or metadata.get("api_prompt_policy_version")
            or metadata.get("policy_version")
            or ""
        ).strip()
        if prompt_policy_version == COMPILED_IMAGE_API_PROMPT_POLICY_VERSION:
            compiled_v2_items.append(item_id)
    if missing:
        return {"updated": [], "missing": missing}
    if compiled_v2_items:
        item_list = ", ".join(compiled_v2_items)
        raise ValueError(
            f"manual_prompt_update_rejected_for_compiled_v2: {item_list}; "
            "plan and manifest recompilation is required to refresh first_frame_visual_plan, "
            "api_prompt_payload, drawable_prompt_ir, compiler/source lineage, and request snapshot"
        )
    snapshot_path = run_dir / REQUEST_SNAPSHOT_FILE_BY_KIND[kind]
    existing_snapshot: ImageRequestSnapshot | None = None
    if snapshot_path.exists():
        existing_snapshot = load_request_snapshot(snapshot_path, run_dir=run_dir, verify_references=True)
    updated: list[str] = []
    next_text = text
    for item_id, prompt in prompts_by_id.items():
        section_match = re.search(rf"(?m)^##\s+{re.escape(item_id)}\s*$", next_text)
        if not section_match:
            missing.append(item_id)
            break
        next_heading = re.search(r"(?m)^##\s+", next_text[section_match.end() :])
        section_end = section_match.end() + next_heading.start() if next_heading else len(next_text)
        section = next_text[section_match.start() : section_end]
        metadata = _parse_metadata(_metadata_without_fences(section))
        prompt_policy_version = str(
            metadata.get("prompt_policy_version")
            or metadata.get("api_prompt_policy_version")
            or metadata.get("policy_version")
            or ""
        ).strip()
        fence_label = "api_prompt" if prompt_policy_version.startswith(IMAGE_API_PROMPT_POLICY_PREFIX) else r"(?:api_prompt|text|txt)?"
        fence_pattern = re.compile(
            rf"(?ms)(^```{fence_label}[^\n]*\n)(.*?)(\n```[ \t]*$)"
        )
        next_section, count = fence_pattern.subn(
            lambda match, value=prompt.strip(): f"{match.group(1)}{value}{match.group(3)}",
            section,
            count=1,
        )
        if not count:
            if not allow_inline_prompt:
                missing.append(item_id)
                break
            first_newline = section.find("\n")
            if first_newline == -1:
                missing.append(item_id)
                break
            heading = section[:first_newline].rstrip()
            body = section[first_newline + 1 :]
            if prompt_policy_version.startswith(IMAGE_API_PROMPT_POLICY_PREFIX):
                metadata_block = _metadata_without_fences(body)
            else:
                _old_prompt, metadata_block, _debug_prompt_source = _extract_request_prompt(
                    body,
                    prompt_policy_version=prompt_policy_version or None,
                )
            metadata = metadata_block.rstrip()
            inline_fence_label = "api_prompt" if prompt_policy_version.startswith(IMAGE_API_PROMPT_POLICY_PREFIX) else "text"
            next_section = f"{heading}\n{metadata}\n\n```{inline_fence_label}\n{prompt.strip()}\n```\n"
        next_text = next_text[: section_match.start()] + next_section + next_text[section_end:]
        updated.append(item_id)
    if missing:
        return {"updated": [], "missing": missing}
    if updated:
        _atomic_write_text(path, next_text if next_text.endswith("\n") else next_text + "\n")
        if existing_snapshot is not None:
            updated_items = parse_request_markdown(next_text, kind=kind, run_dir=run_dir)
            snapshot_source_by_id = {item.item_id: item for item in existing_snapshot.items}
            if {item.id for item in updated_items} != set(snapshot_source_by_id):
                raise ImageRequestSnapshotError("cannot rematerialize snapshot: request item ids changed")
            snapshot = materialize_request_snapshot(
                run_dir,
                kind=kind,
                items=[
                    {
                        "item_id": item.id,
                        "kind": kind,
                        "destination": item.output,
                        "prompt": item.prompt,
                        "prompt_policy_version": item.prompt_policy_version,
                        "compiler_version": snapshot_source_by_id[item.id].compiler_version,
                        "source_digest": snapshot_source_by_id[item.id].source_digest,
                        "references": list(item.references),
                    }
                    for item in updated_items
                ],
                source_artifact=filename,
            )
            write_request_snapshot_atomic(snapshot_path, snapshot, run_dir=run_dir)
    return {"updated": updated, "missing": missing}


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as temporary_file:
            temporary_file.write(text)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def list_reference_options(run_dir: Path) -> list[ReferenceOption]:
    assets = run_dir / "assets"
    if not assets.exists():
        return []
    options: list[ReferenceOption] = []
    for path in sorted(p for p in assets.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES):
        rel = path.relative_to(run_dir).as_posix()
        options.append(ReferenceOption(path=rel, label=path.stem))
    return options


def candidate_dir(run_dir: Path, item_id: str) -> Path:
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", item_id).strip("_") or "item"
    if safe_id in {".", ".."}:
        raise ValueError("item_id cannot be a dot segment")
    base = run_dir / "assets" / "test" / "image_gen_candidates"
    directory = base / safe_id
    resolved = directory.resolve()
    resolved_base = base.resolve()
    if resolved_base not in resolved.parents:
        raise ValueError("item_id escapes image candidate root")
    return directory


def candidate_path(run_dir: Path, item_id: str, index: int) -> Path:
    safe_id = candidate_dir(run_dir, item_id).name
    return candidate_dir(run_dir, item_id) / f"{safe_id}_candidate_{index:02d}.png"


def list_candidate_items(run_dir: Path, item_id: str) -> list[dict[str, Any]]:
    directory = candidate_dir(run_dir, item_id)
    if not directory.exists():
        return []
    candidates: list[dict[str, Any]] = []
    for path in sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES):
        match = re.search(r"candidate_(\d+)", path.stem)
        index = int(match.group(1)) if match else len(candidates) + 1
        try:
            validate_image_bytes(path)
        except ValueError:
            continue
        candidates.append(
            {
                "index": index,
                "status": "completed",
                "path": path.relative_to(run_dir).as_posix(),
                "revisedPrompt": None,
                "mtimeMs": int(path.stat().st_mtime * 1000),
            }
        )
    return candidates


def _run_relative_or_string(run_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return str(path)


def _path_debug_details(run_dir: Path, path: Path) -> dict[str, Any]:
    details: dict[str, Any] = {
        "path": _run_relative_or_string(run_dir, path),
        "exists": path.exists(),
        "isFile": path.is_file(),
    }
    try:
        stat = path.stat()
    except OSError as exc:
        details["statError"] = str(exc)
        return details
    details["sizeBytes"] = stat.st_size
    details["mtimeMs"] = int(stat.st_mtime * 1000)
    return details


def write_app_server_image_debug_log(
    *,
    run_dir: Path,
    item_id: str,
    index: int,
    destination: Path,
    references: list[Path],
    prompt: str | None = None,
    kind: str | None = None,
    prompt_policy_version: str | None = None,
    debug_prompt_source: dict[str, Any] | None = None,
    request_revision: str | None = None,
    request_digest: str | None = None,
    compiler_version: str | None = None,
    source_digest: str | None = None,
    result: Any | None = None,
    error: str | None = None,
) -> Path:
    log_dir = run_dir / "logs" / "app_server" / "image_gen"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", item_id).strip("_") or "item"
    log_path = log_dir / f"{stamp}_{time.time_ns()}_{safe_id}_candidate_{index:02d}.json"
    transcript = getattr(result, "transcript", []) if result is not None else []
    result_reference_sha256s = getattr(result, "reference_sha256s", None) if result is not None else None
    reference_sha256s = result_reference_sha256s if isinstance(result_reference_sha256s, list) else []
    output_sha256 = _sha256_file(destination) if destination.exists() and destination.is_file() else None
    provenance = {
        "policy": getattr(result, "provenance_policy", None) if result is not None else None,
        "generationJobId": getattr(result, "generation_job_id", None) if result is not None else None,
        "itemId": getattr(result, "item_id", None) if result is not None else None,
        "turnId": getattr(result, "turn_id", None) if result is not None else None,
        "promptSha256": getattr(result, "prompt_sha256", None) if result is not None else None,
        "referenceSha256s": reference_sha256s,
        "imageGenerationItemId": getattr(result, "image_generation_item_id", None) if result is not None else None,
        "imageGenerationItemCount": getattr(result, "image_generation_item_count", 0) if result is not None else 0,
        "savedPath": str(getattr(result, "saved_path", "") or "") if result is not None else "",
        "destination": getattr(result, "destination", None) if result is not None else None,
        "outputSha256": output_sha256,
        "requestRevision": request_revision,
        "requestDigest": request_digest,
        "compilerVersion": compiler_version,
        "sourceDigest": source_digest,
        "source": getattr(result, "source", None) if result is not None else None,
        "authoritative": bool(getattr(result, "provenance_authoritative", False)) if result is not None else False,
    }
    payload = {
        "loggedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "itemId": item_id,
        "candidateIndex": index,
        "kind": kind,
        "destination": _run_relative_or_string(run_dir, destination),
        "destinationDetails": _path_debug_details(run_dir, destination),
        "references": [_run_relative_or_string(run_dir, reference) for reference in references],
        "referenceDetails": [_path_debug_details(run_dir, reference) for reference in references],
        "referenceCount": len(references),
        "prompt": prompt,
        "promptLength": len(prompt or ""),
        "promptSha256": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest() if prompt is not None else None,
        "referenceSha256s": reference_sha256s,
        "outputSha256": output_sha256,
        "generationJobId": provenance["generationJobId"],
        "turnId": provenance["turnId"],
        "imageGenerationItemId": provenance["imageGenerationItemId"],
        "imageGenerationItemCount": provenance["imageGenerationItemCount"],
        "provenance": provenance,
        "provenanceAuthoritative": provenance["authoritative"],
        "requestRevision": request_revision,
        "requestDigest": request_digest,
        "compilerVersion": compiler_version,
        "sourceDigest": source_digest,
        "apiPromptPolicyVersion": prompt_policy_version,
        "debugPromptSource": debug_prompt_source or {},
        "status": (
            "failed"
            if error
            else (getattr(result, "status", "missing") if result is not None else "missing")
        ),
        "savedPath": str(getattr(result, "saved_path", "") or ""),
        "source": getattr(result, "source", None) if result is not None else None,
        "revisedPrompt": getattr(result, "revised_prompt", None) if result is not None else None,
        "error": error,
        "transcript": transcript if isinstance(transcript, list) else [],
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index_path = run_dir / "logs" / "image_generation_prompts.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as index_file:
        index_file.write(json.dumps({**payload, "debugLog": _run_relative_or_string(run_dir, log_path)}, ensure_ascii=False) + "\n")
    return log_path


def write_app_server_debug_log(
    *,
    run_dir: Path,
    operation: str,
    status: str,
    item_id: str | None = None,
    request: dict[str, Any] | None = None,
    response: dict[str, Any] | None = None,
    transcript: list[dict[str, Any]] | None = None,
    error: str | None = None,
) -> Path:
    safe_operation = re.sub(r"[^a-zA-Z0-9_.-]+", "_", operation).strip("_") or "operation"
    log_dir = run_dir / "logs" / "app_server" / safe_operation
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", item_id or "operation").strip("_") or "operation"
    log_path = log_dir / f"{stamp}_{time.time_ns()}_{safe_id}.json"
    payload = {
        "loggedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "operation": operation,
        "itemId": item_id,
        "status": status,
        "request": request or {},
        "response": response or {},
        "transcript": transcript or [],
        "error": error,
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    index_path = run_dir / "logs" / "app_server" / "events.jsonl"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as index_file:
        index_file.write(json.dumps({**payload, "debugLog": _run_relative_or_string(run_dir, log_path)}, ensure_ascii=False) + "\n")
    return log_path


def copy_saved_image(saved_path: Path, destination: Path) -> Path:
    if not saved_path.exists() or not saved_path.is_file():
        raise FileNotFoundError(f"saved image not found: {saved_path}")
    require_image_file(saved_path)
    validate_image_bytes(saved_path)
    if destination.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("destination must be an image file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if saved_path.resolve() == destination.resolve():
        return destination
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=destination.suffix,
        dir=destination.parent,
    )
    os.close(file_descriptor)
    temporary_path = Path(temporary_name)
    try:
        shutil.copy2(saved_path, temporary_path)
        validate_image_bytes(temporary_path)
        with temporary_path.open("rb") as temporary_file:
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
    return destination


def copy_saved_image_to_new_candidate(
    saved_path: Path,
    *,
    run_dir: Path,
    item_id: str,
    requested_index: int,
) -> tuple[Path, int]:
    """Import a candidate while treating every existing candidate as immutable."""
    if requested_index < 1:
        raise ValueError("requested_index must be positive")
    directory = candidate_dir(run_dir, item_id)
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".candidate_import.lock"
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        existing_indices = []
        for path in directory.iterdir():
            match = re.search(r"candidate_(\d+)", path.stem)
            if path.is_file() and match:
                existing_indices.append(int(match.group(1)))
        destination = candidate_path(run_dir, item_id, requested_index)
        actual_index = requested_index
        if destination.exists() or requested_index in existing_indices:
            actual_index = max([requested_index, *existing_indices]) + 1
            destination = candidate_path(run_dir, item_id, actual_index)
            while destination.exists():
                actual_index += 1
                destination = candidate_path(run_dir, item_id, actual_index)
        copy_saved_image(saved_path, destination)
        return destination, actual_index


def first_image_retention_root(root: Path | None = None) -> Path:
    configured = os.environ.get("TOC_IMAGE_FIRST_RETENTION_ROOT", "").strip()
    if configured:
        configured_path = Path(configured).expanduser()
        if not configured_path.is_absolute():
            configured_path = (root or repo_root()) / configured_path
        return configured_path.resolve()
    return ((root or repo_root()) / "server" / "data" / "image_first_retention").resolve()


def _retention_component(value: str, *, fallback: str) -> str:
    normalized = re.sub(r"[^\w.-]+", "_", str(value), flags=re.UNICODE).strip("_.-")
    label = (normalized or fallback)[:80]
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]
    return f"{label}--{digest}"


def first_image_retention_dir(
    *,
    root: Path | None,
    run_id: str,
    kind: str,
    item_id: str,
) -> Path:
    if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
        raise ValueError("invalid run_id")
    if kind not in {"asset", "scene"}:
        raise ValueError("invalid image request kind")
    if not item_id.strip():
        raise ValueError("item_id is required")
    return (
        first_image_retention_root(root)
        / "runs"
        / _retention_component(run_id, fallback="run")
        / kind
        / _retention_component(item_id, fallback="item")
    )


def _load_retention_metadata(directory: Path) -> dict[str, Any] | None:
    path = directory / "receipt.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("schemaVersion") != FIRST_IMAGE_RETENTION_SCHEMA:
        return None
    image_name = str(payload.get("imageFile") or "")
    directory_resolved = directory.resolve()
    image_path = (directory / image_name).resolve()
    if not image_name or image_path.parent != directory_resolved or not image_path.is_file():
        return None
    try:
        validate_image_bytes(image_path)
    except ValueError:
        return None
    expected_sha256 = str(payload.get("sha256") or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        return None
    if _sha256_file(image_path) != expected_sha256:
        return None
    return {**payload, "imagePath": str(image_path)}


def _validated_retention_destination(
    retention: dict[str, Any],
    *,
    root: Path | None,
) -> Path:
    run_id = str(retention.get("runId") or "")
    kind = str(retention.get("kind") or "")
    item_id = str(retention.get("itemId") or "")
    storage_role = str(retention.get("storageRole") or "")
    try:
        candidate_index = int(retention.get("candidateIndex") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid retained candidate index") from exc
    if candidate_index < 1:
        raise ValueError("invalid retained candidate index")
    if storage_role not in {"candidate", "canonical"}:
        raise ValueError("invalid retained storage role")
    run_dir = output_root(root) / run_id
    destination_text = str(retention.get("destination") or "").strip()
    if not destination_text:
        raise ValueError("retained destination is required")
    destination = resolve_run_relative(run_dir, destination_text)
    if storage_role == "candidate":
        expected = candidate_path(run_dir, item_id, candidate_index).resolve()
        if destination != expected:
            raise ValueError("retained candidate destination does not match its item and index")
    else:
        require_assets_output(run_dir, destination_text)
    if kind not in {"asset", "scene"}:
        raise ValueError("invalid retained kind")
    return destination


def _validated_retention_metadata(
    directory: Path,
    *,
    root: Path | None,
) -> dict[str, Any] | None:
    payload = _load_retention_metadata(directory)
    if payload is None:
        return None
    run_id = str(payload.get("runId") or "")
    kind = str(payload.get("kind") or "")
    item_id = str(payload.get("itemId") or "")
    try:
        expected_directory = first_image_retention_dir(
            root=root,
            run_id=run_id,
            kind=kind,
            item_id=item_id,
        ).resolve()
        if directory.resolve() != expected_directory:
            return None
        _validated_retention_destination(payload, root=root)
    except (OSError, TypeError, ValueError):
        return None
    return payload


def load_first_image_retention(
    *,
    root: Path | None,
    run_id: str,
    kind: str,
    item_id: str,
) -> dict[str, Any] | None:
    directory = first_image_retention_dir(
        root=root,
        run_id=run_id,
        kind=kind,
        item_id=item_id,
    )
    return _validated_retention_metadata(directory, root=root)


def list_first_image_retentions(
    *,
    root: Path | None = None,
    run_id: str | None = None,
    kind: str | None = None,
    item_id: str | None = None,
) -> list[dict[str, Any]]:
    if run_id is not None and (not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}):
        raise ValueError("invalid run_id")
    if kind is not None and kind not in {"asset", "scene"}:
        raise ValueError("invalid image request kind")
    retention_runs = first_image_retention_root(root) / "runs"
    if not retention_runs.is_dir():
        return []
    records: list[dict[str, Any]] = []
    for receipt in retention_runs.glob("*/*/*/receipt.json"):
        directory = receipt.parent
        try:
            resolved_directory = directory.resolve()
            resolved_root = retention_runs.resolve()
        except OSError:
            continue
        if resolved_root not in resolved_directory.parents:
            continue
        record = _validated_retention_metadata(directory, root=root)
        if record is None:
            continue
        if run_id is not None and record.get("runId") != run_id:
            continue
        if kind is not None and record.get("kind") != kind:
            continue
        if item_id is not None and record.get("itemId") != item_id:
            continue
        records.append(record)
    return sorted(
        records,
        key=lambda record: (
            str(record.get("runId") or ""),
            str(record.get("kind") or ""),
            str(record.get("itemId") or ""),
        ),
    )


def _first_image_retention_restore_marker(run_dir: Path) -> Path:
    return run_dir / FIRST_IMAGE_RETENTION_RESTORE_MARKER


def is_first_image_retention_restored_run(run_dir: Path) -> bool:
    marker = _first_image_retention_restore_marker(run_dir)
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        isinstance(payload, dict)
        and payload.get("schemaVersion") == FIRST_IMAGE_RETENTION_RESTORE_SCHEMA
        and payload.get("runId") == run_dir.name
    )


def restore_first_image_retention_run(
    run_id: str,
    *,
    root: Path | None = None,
) -> Path | None:
    records = list_first_image_retentions(root=root, run_id=run_id)
    if not records:
        return None
    base = output_root(root)
    base.mkdir(parents=True, exist_ok=True)
    run_dir = base / run_id
    resolved_run_dir = run_dir.resolve()
    if base.resolve() not in resolved_run_dir.parents:
        raise ValueError("run_id escapes output root")

    lock_dir = first_image_retention_root(root) / "restore_locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"{_retention_component(run_id, fallback='run')}.lock"
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        created = False
        try:
            run_dir.mkdir(parents=False, exist_ok=False)
            created = True
        except FileExistsError:
            if not run_dir.is_dir() or not is_first_image_retention_restored_run(run_dir):
                return None

        marker_path = _first_image_retention_restore_marker(run_dir)
        if created:
            _atomic_write_text(
                marker_path,
                json.dumps(
                    {
                        "schemaVersion": FIRST_IMAGE_RETENTION_RESTORE_SCHEMA,
                        "runId": run_id,
                        "restoredAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        "restoredItems": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
            )

        restored_items: list[dict[str, Any]] = []
        for record in records:
            source = Path(str(record["imagePath"]))
            candidate_index = int(record.get("candidateIndex") or 1)
            if record.get("storageRole") == "candidate":
                destination = _validated_retention_destination(record, root=root)
            else:
                canonical_preview = candidate_path(
                    run_dir,
                    str(record["itemId"]),
                    candidate_index,
                )
                destination = (
                    canonical_preview
                    if source.suffix.lower() == ".png"
                    else canonical_preview.with_suffix(source.suffix.lower())
                )
            if destination.exists():
                try:
                    validate_image_bytes(destination)
                except (OSError, ValueError):
                    continue
                if _sha256_file(destination) != str(record["sha256"]):
                    continue
            else:
                copy_saved_image(source, destination)
            restored_items.append(
                {
                    "kind": record["kind"],
                    "itemId": record["itemId"],
                    "candidateIndex": candidate_index,
                    "path": destination.resolve().relative_to(run_dir.resolve()).as_posix(),
                    "sha256": record["sha256"],
                }
            )

        if not restored_items:
            if created:
                shutil.rmtree(run_dir)
            return None
        _atomic_write_text(
            marker_path,
            json.dumps(
                {
                    "schemaVersion": FIRST_IMAGE_RETENTION_RESTORE_SCHEMA,
                    "runId": run_id,
                    "restoredAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "restoredItems": restored_items,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )
        return run_dir.resolve()


def retain_first_image(
    source: Path,
    *,
    root: Path | None,
    run_id: str,
    kind: str,
    item_id: str,
    candidate_index: int,
    destination: str,
    provenance: dict[str, Any] | None = None,
    storage_role: str = "candidate",
) -> dict[str, Any]:
    """Keep the first valid raster for one run/kind/item without ever replacing it."""
    if candidate_index < 1:
        raise ValueError("candidate_index must be positive")
    if storage_role not in {"candidate", "canonical"}:
        raise ValueError("invalid first image storage role")
    require_image_file(source)
    validate_image_bytes(source)
    directory = first_image_retention_dir(
        root=root,
        run_id=run_id,
        kind=kind,
        item_id=item_id,
    )
    directory.mkdir(parents=True, exist_ok=True)
    lock_path = directory / ".retain.lock"
    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        existing = _load_retention_metadata(directory)
        if existing is not None:
            return {**existing, "created": False}

        suffix = source.suffix.lower()
        image_path = directory / f"first{suffix}"
        if image_path.exists():
            validate_image_bytes(image_path)
        else:
            copy_saved_image(source, image_path)
        retained_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        metadata: dict[str, Any] = {
            "schemaVersion": FIRST_IMAGE_RETENTION_SCHEMA,
            "runId": run_id,
            "kind": kind,
            "itemId": item_id,
            "candidateIndex": candidate_index,
            "destination": destination,
            "storageRole": storage_role,
            "retainedAt": retained_at,
            "imageFile": image_path.name,
            "sha256": _sha256_file(image_path),
            "sizeBytes": image_path.stat().st_size,
            "sourcePath": str(source),
            "provenance": dict(provenance or {}),
        }
        _atomic_write_text(
            directory / "receipt.json",
            json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        )
        return {**metadata, "imagePath": str(image_path), "created": True}


def rehydrate_retained_first_image(
    run_dir: Path,
    *,
    root: Path | None,
    kind: str,
    item_id: str,
) -> Path | None:
    retention = load_first_image_retention(
        root=root,
        run_id=run_dir.name,
        kind=kind,
        item_id=item_id,
    )
    if retention is None or retention.get("storageRole") != "candidate":
        return None
    destination_text = str(retention.get("destination") or "").strip()
    if not destination_text:
        destination_text = candidate_path(
            run_dir,
            item_id,
            int(retention.get("candidateIndex") or 1),
        ).relative_to(run_dir).as_posix()
    destination = resolve_run_relative(run_dir, destination_text)
    expected_parent = candidate_dir(run_dir, item_id).resolve()
    if destination.parent.resolve() != expected_parent:
        raise ValueError("retained image destination is not an item candidate path")
    if destination.exists():
        validate_image_bytes(destination)
        return destination
    source = Path(str(retention["imagePath"]))
    copy_saved_image(source, destination)
    return destination


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_run_relative(run_dir: Path, path: str) -> Path:
    target = (run_dir / path).resolve()
    base = run_dir.resolve()
    if base not in target.parents and target != base:
        raise ValueError("path escapes run directory")
    return target


def require_image_file(path: Path) -> None:
    if path.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("path must be an image file")


def validate_image_bytes(path: Path) -> None:
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("image file is empty")
    if size > MAX_IMAGE_BYTES:
        raise ValueError("image file is too large")
    header = path.read_bytes()[:16]
    if path.suffix.lower() == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("png file has invalid magic bytes")
    if path.suffix.lower() in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8\xff"):
        raise ValueError("jpeg file has invalid magic bytes")
    if path.suffix.lower() == ".webp" and not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
        raise ValueError("webp file has invalid magic bytes")


def require_assets_output(run_dir: Path, output: str) -> None:
    normalized = Path(output)
    if normalized.is_absolute() or ".." in normalized.parts:
        raise ValueError("output must be a run-relative assets image path")
    if not normalized.parts or normalized.parts[0] != "assets":
        raise ValueError("output must be under assets/")
    require_image_file(normalized)


def require_candidate_path(run_dir: Path, candidate: Path) -> None:
    base = (run_dir / "assets" / "test" / "image_gen_candidates").resolve()
    resolved = candidate.resolve()
    if base not in resolved.parents:
        raise ValueError("candidate must be under assets/test/image_gen_candidates/")
    require_image_file(resolved)


def backup_existing(target: Path, run_dir: Path) -> Path | None:
    if not target.exists():
        return None
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_root = run_dir / "assets" / "test" / "image_gen_backups" / stamp
    backup_root.mkdir(parents=True, exist_ok=True)
    backup = backup_root / target.name
    shutil.copy2(target, backup)
    return backup


def insert_candidate(run_dir: Path, candidate: Path, output: str) -> dict[str, str | None]:
    run_dir = run_dir.resolve()
    require_candidate_path(run_dir, candidate)
    validate_image_bytes(candidate)
    require_assets_output(run_dir, output)
    target = resolve_run_relative(run_dir, output)
    backup = backup_existing(target, run_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(candidate, target)
    return {
        "output": target.relative_to(run_dir).as_posix(),
        "backup": backup.relative_to(run_dir).as_posix() if backup else None,
    }


def build_zip(paths: list[Path], *, base_dir: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in paths:
            if not path.exists() or not path.is_file():
                continue
            try:
                arcname = path.relative_to(base_dir).as_posix()
            except ValueError:
                arcname = path.name
            zf.write(path, arcname)
    return buf.getvalue()


def item_to_api(item: ImageRequestItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "kind": item.kind,
        "assetType": item.asset_type,
        "tool": item.tool,
        "output": item.output,
        "prompt": item.prompt,
        "promptPolicyVersion": item.prompt_policy_version,
        "debugPromptSource": item.debug_prompt_source,
        "references": item.references,
        "referenceCount": item.reference_count,
        "executionLane": item.execution_lane,
        "generationStatus": item.generation_status,
        "existingImage": item.existing_image,
    }


def reference_to_api(option: ReferenceOption) -> dict[str, str]:
    return {"path": option.path, "label": option.label}
