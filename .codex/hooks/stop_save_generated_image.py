#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_PATH = REPO_ROOT / ".codex" / "hooks" / ".stop_save_generated_image_state.json"
CODEX_HOME = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
GENERATED_IMAGES_DIR = CODEX_HOME / "generated_images"
HISTORY_PATH = CODEX_HOME / "history.jsonl"
SAVE_KEYWORDS = ("保存", "save", "コピー", "copy", "差し替え", "保存する", "保存して")


def _load_stdin() -> dict[str, Any]:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state: dict[str, Any]) -> None:
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _iter_session_texts(session_id: str) -> list[str]:
    if not session_id or not HISTORY_PATH.exists():
        return []
    texts: list[str] = []
    for line in HISTORY_PATH.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("session_id") != session_id:
            continue
        text = obj.get("text")
        if isinstance(text, str) and text.strip():
            texts.append(text)
    return texts


def _newest_generated_image() -> Path | None:
    if not GENERATED_IMAGES_DIR.exists():
        return None
    candidates = sorted(GENERATED_IMAGES_DIR.glob("*/*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def _has_save_intent(text: str) -> bool:
    lowered = text.lower()
    return any(k in text or k in lowered for k in SAVE_KEYWORDS)


def _normalize_repo_path(raw: str) -> Path:
    p = Path(raw)
    if p.is_absolute():
        return p
    return (REPO_ROOT / raw).resolve()


def _extract_explicit_path(text: str) -> Path | None:
    patterns = [
        r"(/Users/[^\s'\"`]+?\.(?:png|jpg|jpeg|webp))",
        r"((?:output|assets)/[^\s'\"`]+?\.(?:png|jpg|jpeg|webp))",
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if not m:
            continue
        return _normalize_repo_path(m.group(1))
    return None


def _infer_scene_destination(text: str) -> Path | None:
    patterns = [
        r"scene\s*0*(\d+)[_ ]cut\s*0*(\d+)",
        r"scene\s*0*(\d+)[_ ]0*(\d+)",
        r"\b0*(\d+)[_ ]0*(\d+)\b",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE):
            scene_num = int(m.group(1))
            cut_num = int(m.group(2))
            glob_pattern = f"output/*/assets/scenes/scene{scene_num:02d}_cut{cut_num:02d}.png"
            matches = sorted(REPO_ROOT.glob(glob_pattern))
            if len(matches) == 1:
                return matches[0]
    return None


def _resolve_destination(session_texts: list[str]) -> Path | None:
    recent = "\n".join(session_texts[-8:])
    if not _has_save_intent(recent):
        return None
    explicit = _extract_explicit_path(recent)
    if explicit is not None:
        return explicit
    return _infer_scene_destination(recent)


def _noop(message: str | None = None) -> int:
    payload: dict[str, Any] = {"continue": True}
    if message:
        payload["systemMessage"] = message
    json.dump(payload, sys.stdout, ensure_ascii=False)
    return 0


def main() -> int:
    payload = _load_stdin()
    session_id = str(payload.get("session_id") or "")
    latest_image = _newest_generated_image()
    if latest_image is None:
        return _noop()

    session_texts = _iter_session_texts(session_id)
    destination = _resolve_destination(session_texts)
    if destination is None:
        return _noop()

    state = _load_state()
    latest_key = f"{latest_image.resolve()}::{latest_image.stat().st_mtime_ns}"
    destination_key = str(destination.resolve())
    if state.get("last_copy") == {"image": latest_key, "destination": destination_key}:
        return _noop()

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(latest_image, destination)
    state["last_copy"] = {"image": latest_key, "destination": destination_key}
    _save_state(state)
    return _noop(f"Saved generated image to {destination}")


if __name__ == "__main__":
    raise SystemExit(main())
