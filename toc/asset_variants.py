"""Immutable, region-bounded image variants for production candidates."""

from __future__ import annotations

import hashlib
import io
import json
import math
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from PIL import Image, ImageOps

from scripts.world_walk_source import read_regular_file_nofollow
from toc.image_request_snapshot import write_run_file_atomic_nofollow


class AssetVariantError(ValueError):
    """An image variant request is invalid or its inputs are stale/unsafe."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ITEM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _safe_relative(root: Path, value: str | Path, *, field: str) -> tuple[str, Path]:
    raw = str(value)
    pure = PurePosixPath(raw)
    if not raw or pure.is_absolute() or "\\" in raw or any(p in ("", ".", "..") for p in pure.parts):
        raise AssetVariantError(f"{field} must be a safe run-relative path")
    if pure.parts and ":" in pure.parts[0]:
        raise AssetVariantError(f"{field} must be a safe run-relative path")
    root_abs = Path(root).absolute()
    path = root_abs.joinpath(*pure.parts)
    current = root_abs
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise AssetVariantError(f"{field} must not traverse symlinks")
    try:
        path.resolve(strict=False).relative_to(root_abs.resolve(strict=True))
    except (ValueError, FileNotFoundError) as exc:
        raise AssetVariantError(f"{field} escapes the run directory") from exc
    return pure.as_posix(), path


def _read_image(root: Path, value: str | Path, *, field: str) -> tuple[str, Image.Image, bytes]:
    rel, _ = _safe_relative(root, value, field=field)
    try:
        raw = read_regular_file_nofollow(root, rel)
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            oriented = ImageOps.exif_transpose(image)
            # Palette transparency lives in image.info rather than getbands().
            mode = "RGBA" if "A" in oriented.getbands() or oriented.info.get("transparency") is not None else "RGB"
            pixels = oriented.convert(mode).copy()
    except (OSError, ValueError) as exc:
        raise AssetVariantError(f"{field} must be an existing readable image") from exc
    return rel, pixels, raw


def _validate_hash(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise AssetVariantError(f"{field} must be 64 lowercase hexadecimal characters")


def _pixel_box(region: Mapping[str, Any], width: int, height: int) -> list[int]:
    try:
        values = [region[key] for key in ("x", "y", "width", "height")]
    except (KeyError, TypeError) as exc:
        raise AssetVariantError("each region needs x, y, width, and height") from exc
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise AssetVariantError("region coordinates must be finite numbers")
    x, y, rw, rh = (float(v) for v in values)
    if x < 0 or y < 0 or rw <= 0 or rh <= 0 or x + rw > 1 or y + rh > 1:
        raise AssetVariantError("regions must be non-empty rectangles inside normalized 0..1 bounds")
    left, top = math.floor(x * width), math.floor(y * height)
    right, bottom = math.ceil((x + rw) * width), math.ceil((y + rh) * height)
    right, bottom = min(width, right), min(height, bottom)
    if left >= right or top >= bottom:
        raise AssetVariantError("region maps to an empty pixel rectangle")
    return [left, top, right, bottom]


def create_variant(
    root: Path,
    *,
    item_id: str,
    base_path: str | Path,
    edited_path: str | Path,
    base_sha256: str,
    edited_sha256: str,
    regions: list[Mapping[str, Any]],
    state_description: str,
) -> dict[str, Any]:
    """Copy edited pixels only within selected normalized regions into a new PNG."""
    if not isinstance(item_id, str) or not _ITEM_ID.fullmatch(item_id):
        raise AssetVariantError("item_id is invalid")
    _validate_hash(base_sha256, field="base_sha256")
    _validate_hash(edited_sha256, field="edited_sha256")
    if not isinstance(state_description, str) or not state_description.strip():
        raise AssetVariantError("state_description is required")
    if not isinstance(regions, list) or not regions:
        raise AssetVariantError("at least one editable region is required")
    run = Path(root).absolute()
    base_rel, base, base_bytes = _read_image(run, base_path, field="base_path")
    edited_rel, edited, edited_bytes = _read_image(run, edited_path, field="edited_path")
    actual_base_hash, actual_edited_hash = _sha256(base_bytes), _sha256(edited_bytes)
    if actual_base_hash != base_sha256:
        raise AssetVariantError("base_sha256 is stale")
    if actual_edited_hash != edited_sha256:
        raise AssetVariantError("edited_sha256 is stale")
    if base.size != edited.size:
        raise AssetVariantError("base and edited images must have equal display dimensions")
    boxes = [_pixel_box(region, *base.size) for region in regions]
    output = base.copy()
    for left, top, right, bottom in boxes:
        output.paste(edited.crop((left, top, right, bottom)), (left, top))
    variant_id = str(uuid.uuid4())
    image_rel = f"assets/test/state_variants/{item_id}/{variant_id}.png"
    receipt_rel = f"assets/test/state_variants/{item_id}/{variant_id}.json"
    _, image_path = _safe_relative(run, image_rel, field="variant output")
    _, receipt_path = _safe_relative(run, receipt_rel, field="variant receipt")
    image_path.parent.mkdir(parents=True, exist_ok=True)
    # Reject a symlink introduced while creating directories.
    _safe_relative(run, image_rel, field="variant output")
    import io
    image_buffer = io.BytesIO()
    output.save(image_buffer, format="PNG", optimize=False)
    image_bytes = image_buffer.getvalue()
    record = {
        "schema_version": "toc.asset_state_variant.v1",
        "variant_id": variant_id,
        "item_id": item_id,
        "path": image_rel,
        "base_path": base_rel,
        "base_sha256": actual_base_hash,
        "edited_path": edited_rel,
        "edited_sha256": actual_edited_hash,
        "sha256": _sha256(image_bytes),
        "width": base.width,
        "height": base.height,
        "regions": [{"x": r[0], "y": r[1], "width": r[2] - r[0], "height": r[3] - r[1]} for r in boxes],
        "state_description": state_description.strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "receipt_path": receipt_rel,
    }
    # Bind the output to sources still current after decoding and pixel composition.
    try:
        latest_base = _sha256(read_regular_file_nofollow(run, base_rel))
        latest_edited = _sha256(read_regular_file_nofollow(run, edited_rel))
    except (OSError, ValueError) as exc:
        raise AssetVariantError("base or edited image changed while composing variant") from exc
    if latest_base != actual_base_hash or latest_edited != actual_edited_hash:
        raise AssetVariantError("base or edited image changed while composing variant")
    # Writer publishes exclusively for these UUID paths and does not follow links.
    try:
        write_run_file_atomic_nofollow(image_path, image_bytes, run_dir=run)
        receipt_bytes = (json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
        write_run_file_atomic_nofollow(receipt_path, receipt_bytes, run_dir=run)
    except Exception:
        # Keep any already-published files as immutable evidence; callers can list only complete pairs.
        raise
    return record


def list_variants(root: Path, item_id: str) -> list[dict[str, Any]]:
    """List variant receipts for an item and report source/output drift."""
    if not isinstance(item_id, str) or not _ITEM_ID.fullmatch(item_id):
        raise AssetVariantError("item_id is invalid")
    run = Path(root).absolute()
    directory = run / "assets" / "test" / "state_variants" / item_id
    if not directory.exists():
        return []
    _safe_relative(run, directory.relative_to(run), field="variant directory")
    records: list[dict[str, Any]] = []
    for receipt in sorted(directory.glob("*.json")):
        _safe_relative(run, receipt.relative_to(run), field="variant receipt")
        try:
            record = json.loads(receipt.read_text(encoding="utf-8"))
            if record.get("item_id") != item_id or record.get("receipt_path") != receipt.relative_to(run).as_posix():
                raise AssetVariantError("variant receipt identity mismatch")
            stale = False
            for path_key, hash_key in (("base_path", "base_sha256"), ("edited_path", "edited_sha256"), ("path", "sha256")):
                _safe_relative(run, record[path_key], field=path_key)
                try:
                    actual = _sha256(read_regular_file_nofollow(run, record[path_key]))
                except (OSError, ValueError):
                    actual = None
                stale |= actual != record.get(hash_key)
            record["stale"] = bool(stale)
            records.append(record)
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise AssetVariantError(f"invalid variant receipt: {receipt}") from exc
    return records
