from __future__ import annotations

import io
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


@dataclass(frozen=True)
class ImageRequestItem:
    id: str
    kind: str
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


def parse_request_markdown(text: str, *, kind: str, run_dir: Path) -> list[ImageRequestItem]:
    parts = re.split(r"(?m)^##\s+(.+?)\s*$", text)
    items: list[ImageRequestItem] = []
    for index in range(1, len(parts), 2):
        item_id = parts[index].strip()
        section = parts[index + 1]
        prompt_match = re.search(r"```(?:text|txt)?\s*\n(.*?)\n```", section, flags=re.DOTALL)
        prompt = prompt_match.group(1).strip() if prompt_match else ""
        metadata_block = section[: prompt_match.start()] if prompt_match else section
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
    return run_dir / "assets" / "test" / "image_gen_candidates" / safe_id


def candidate_path(run_dir: Path, item_id: str, index: int) -> Path:
    return candidate_dir(run_dir, item_id) / f"candidate_{index:02d}.png"


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
