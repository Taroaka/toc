from __future__ import annotations

import io
import json
import re
import shutil
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
MAX_IMAGE_BYTES = 50 * 1024 * 1024
REQUEST_FILE_BY_KIND = {
    "asset": "asset_generation_requests.md",
    "scene": "image_generation_requests.md",
}
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
    if not base.exists():
        return []
    runs: list[dict[str, Any]] = []
    for path in sorted((p for p in base.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True):
        runs.append(
            {
                "id": path.name,
                "name": path.name,
                "path": f"output/{path.name}",
                "hasAssetRequests": (path / REQUEST_FILE_BY_KIND["asset"]).exists(),
                "hasSceneRequests": (path / REQUEST_FILE_BY_KIND["scene"]).exists(),
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
            in_references = True
            if value and value not in {"[]", "`[]`"}:
                metadata["references"].append(_strip_ticks(value))
            continue
        if in_references and stripped.startswith("- `"):
            # Format: - `label`: `assets/foo.png`
            match = re.search(r":\s*`([^`]+)`\s*$", stripped)
            if match:
                metadata["references"].append(match.group(1).strip())
                continue
        if in_references and stripped.startswith("- "):
            metadata["references"].append(_strip_ticks(stripped[2:]))
            continue
        match = re.match(r"-\s*([a-zA-Z0-9_ -]+):\s*(.*)$", stripped)
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


def _extract_request_prompt(section: str) -> tuple[str, str]:
    prompt_match = re.search(r"```(?:text|txt)?\s*\n(.*?)\n```", section, flags=re.DOTALL)
    if prompt_match:
        return prompt_match.group(1).strip(), section[: prompt_match.start()]
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
    return "\n".join(prompt_lines).strip(), "\n".join(metadata_lines)


def parse_request_markdown(text: str, *, kind: str, run_dir: Path) -> list[ImageRequestItem]:
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", text)
    items: list[ImageRequestItem] = []
    for index in range(1, len(parts), 2):
        item_id = parts[index].strip()
        section = parts[index + 1]
        prompt, metadata_block = _extract_request_prompt(section)
        metadata = _parse_metadata(metadata_block)
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
    return parse_request_markdown(path.read_text(encoding="utf-8"), kind=kind, run_dir=run_dir)


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
    updated: list[str] = []
    missing: list[str] = []
    next_text = text
    for item_id, prompt in prompts_by_id.items():
        section_match = re.search(rf"(?m)^##\s+{re.escape(item_id)}\s*$", next_text)
        if not section_match:
            missing.append(item_id)
            break
        next_heading = re.search(r"(?m)^##\s+", next_text[section_match.end() :])
        section_end = section_match.end() + next_heading.start() if next_heading else len(next_text)
        section = next_text[section_match.start() : section_end]
        fence_pattern = re.compile(r"(?ms)(```(?:text|txt)?\s*\n)(.*?)(\n```)")
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
            _old_prompt, metadata_block = _extract_request_prompt(body)
            metadata = metadata_block.rstrip()
            next_section = f"{heading}\n{metadata}\n\n```text\n{prompt.strip()}\n```\n"
        next_text = next_text[: section_match.start()] + next_section + next_text[section_end:]
        updated.append(item_id)
    if missing:
        return {"updated": [], "missing": missing}
    if updated:
        path.write_text(next_text if next_text.endswith("\n") else next_text + "\n", encoding="utf-8")
    return {"updated": updated, "missing": missing}


def list_reference_options(run_dir: Path) -> list[ReferenceOption]:
    assets = run_dir / "assets"
    if not assets.exists():
        return []
    options: list[ReferenceOption] = []
    for path in sorted(p for p in assets.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES):
        rel = path.relative_to(run_dir).as_posix()
        options.append(ReferenceOption(path=rel, label=path.stem))
    return options


def _safe_candidate_item_id(item_id: str) -> str:
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", item_id).strip("_") or "item"
    return safe_id


def candidate_dir(run_dir: Path, item_id: str, output: str | None = None) -> Path:
    safe_id = _safe_candidate_item_id(item_id)
    output_value = (output or "").strip()
    if output_value:
        try:
            require_assets_output(run_dir, output_value)
            output_path = resolve_run_relative(run_dir, output_value)
            if output_path.parent.name != "image_gen_candidates":
                return output_path.parent / "image_gen_candidates" / safe_id
        except ValueError:
            pass
    return run_dir / "assets" / "image_gen_candidates" / safe_id


def candidate_path(run_dir: Path, item_id: str, index: int, output: str | None = None) -> Path:
    return candidate_dir(run_dir, item_id, output=output) / f"candidate_{index:02d}.png"


def _candidate_dirs(run_dir: Path, item_id: str) -> list[Path]:
    safe_id = _safe_candidate_item_id(item_id)
    assets = run_dir / "assets"
    directories: list[Path] = []
    primary = assets / "image_gen_candidates" / safe_id
    if primary.exists():
        directories.append(primary)
    if assets.exists():
        for parent in sorted(assets.rglob("image_gen_candidates")):
            directory = parent / safe_id
            if directory.exists() and directory not in directories:
                directories.append(directory)
    legacy = assets / "test" / "image_gen_candidates" / safe_id
    if legacy.exists() and legacy not in directories:
        directories.append(legacy)
    return directories


def list_candidate_items(run_dir: Path, item_id: str) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for directory in _candidate_dirs(run_dir, item_id):
        for path in sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
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
    return sorted(candidates, key=lambda item: (int(item["index"]), str(item["path"])))


def _run_relative_or_string(run_dir: Path, path: Path) -> str:
    try:
        return path.relative_to(run_dir).as_posix()
    except ValueError:
        return str(path)


def write_app_server_image_debug_log(
    *,
    run_dir: Path,
    item_id: str,
    index: int,
    destination: Path,
    references: list[Path],
    result: Any | None = None,
    error: str | None = None,
) -> Path:
    log_dir = run_dir / "logs" / "app_server" / "image_gen"
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", item_id).strip("_") or "item"
    log_path = log_dir / f"{stamp}_{time.time_ns()}_{safe_id}_candidate_{index:02d}.json"
    transcript = getattr(result, "transcript", []) if result is not None else []
    payload = {
        "itemId": item_id,
        "candidateIndex": index,
        "destination": _run_relative_or_string(run_dir, destination),
        "references": [_run_relative_or_string(run_dir, reference) for reference in references],
        "status": getattr(result, "status", "exception" if error else "missing") if result is not None else "exception",
        "savedPath": str(getattr(result, "saved_path", "") or ""),
        "source": getattr(result, "source", None) if result is not None else None,
        "revisedPrompt": getattr(result, "revised_prompt", None) if result is not None else None,
        "error": error,
        "transcript": transcript if isinstance(transcript, list) else [],
    }
    log_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return log_path


def copy_saved_image(saved_path: Path, destination: Path) -> Path:
    if not saved_path.exists() or not saved_path.is_file():
        raise FileNotFoundError(f"saved image not found: {saved_path}")
    require_image_file(saved_path)
    validate_image_bytes(saved_path)
    if destination.suffix.lower() not in IMAGE_SUFFIXES:
        raise ValueError("destination must be an image file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(saved_path, destination)
    return destination


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
    resolved = candidate.resolve()
    assets = (run_dir / "assets").resolve()
    if assets not in resolved.parents:
        raise ValueError("candidate must be under assets/")
    if "image_gen_candidates" not in resolved.parts:
        raise ValueError("candidate must be under an image_gen_candidates directory")
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
        "references": item.references,
        "referenceCount": item.reference_count,
        "executionLane": item.execution_lane,
        "generationStatus": item.generation_status,
        "existingImage": item.existing_image,
    }


def reference_to_api(option: ReferenceOption) -> dict[str, str]:
    return {"path": option.path, "label": option.label}
