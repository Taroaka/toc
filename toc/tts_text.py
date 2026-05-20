from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PronunciationAlias:
    surface: str
    alias: str


@dataclass(frozen=True)
class PreparedTtsText:
    text: str
    applied_aliases: tuple[str, ...]


def _alias_from_mapping(value: dict[str, Any]) -> PronunciationAlias | None:
    surface = str(value.get("surface") or value.get("string_to_replace") or value.get("from") or "").strip()
    alias = str(value.get("alias") or value.get("reading") or value.get("to") or "").strip()
    if not surface or not alias or surface == alias:
        return None
    return PronunciationAlias(surface=surface, alias=alias)


def parse_pronunciation_aliases(raw: str) -> tuple[PronunciationAlias, ...]:
    text = raw.strip()
    if not text:
        return ()
    if text.startswith("{") or text.startswith("["):
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            if isinstance(loaded.get("aliases"), list):
                source = loaded["aliases"]
            else:
                source = [{"surface": key, "alias": value} for key, value in loaded.items()]
        elif isinstance(loaded, list):
            source = loaded
        else:
            raise ValueError("pronunciation aliases JSON must be an object or list")
        aliases = [
            alias
            for item in source
            if isinstance(item, dict) and (alias := _alias_from_mapping(item)) is not None
        ]
        return _dedupe_aliases(aliases)

    aliases: list[PronunciationAlias] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=>" in stripped:
            surface, alias = stripped.split("=>", 1)
        elif "\t" in stripped:
            surface, alias = stripped.split("\t", 1)
        else:
            raise ValueError("pronunciation alias lines must use TAB or =>")
        item = _alias_from_mapping({"surface": surface, "alias": alias})
        if item is not None:
            aliases.append(item)
    return _dedupe_aliases(aliases)


def load_pronunciation_aliases(path: str | Path | None) -> tuple[PronunciationAlias, ...]:
    if path is None or str(path).strip() == "":
        return ()
    return parse_pronunciation_aliases(Path(path).read_text(encoding="utf-8"))


def prepare_elevenlabs_tts_text(
    text: str,
    *,
    pronunciation_aliases: tuple[PronunciationAlias, ...] = (),
) -> PreparedTtsText:
    prepared = _normalize_tts_whitespace(text)
    applied: list[str] = []
    for alias in sorted(pronunciation_aliases, key=lambda item: len(item.surface), reverse=True):
        if alias.surface not in prepared:
            continue
        prepared = prepared.replace(alias.surface, alias.alias)
        applied.append(alias.surface)
    return PreparedTtsText(text=prepared, applied_aliases=tuple(applied))


def _normalize_tts_whitespace(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"[ \t]+\n", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    normalized = re.sub(r"\s+([、。！？!?])", r"\1", normalized)
    return normalized.strip()


def _dedupe_aliases(aliases: list[PronunciationAlias]) -> tuple[PronunciationAlias, ...]:
    seen: set[str] = set()
    out: list[PronunciationAlias] = []
    for alias in aliases:
        if alias.surface in seen:
            continue
        seen.add(alias.surface)
        out.append(alias)
    return tuple(out)
