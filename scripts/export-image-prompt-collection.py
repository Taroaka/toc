#!/usr/bin/env python3
"""Export reviewable image prompt collections from a manifest."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import yaml


def load_manifest_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    match = re.search(r"```yaml\n(.*)\n```", text, re.S)
    if not match:
        raise SystemExit(f"YAML block not found in manifest: {path}")
    return yaml.safe_load(match.group(1))


PROMPT_ENTRY_RE = re.compile(
    r"^##\s+scene(?P<scene_id>\d+)_cut(?P<cut_id>\d+)\n(?P<body>.*?)(?=^##\s+scene\d+_cut\d+\n|\Z)",
    re.M | re.S,
)


@dataclass
class ExistingReviewState:
    agent_review_ok: bool
    human_review_ok: bool
    agent_review_reason_keys: list[str]
    agent_review_reason_messages: list[str]


def _extract_bool_bullet(body: str, key: str, default: bool) -> bool:
    match = re.search(rf"^- {re.escape(key)}:\s+`(?P<value>true|false)`\s*$", body, re.M)
    if not match:
        return default
    return match.group("value") == "true"


def _extract_backtick_bullet(body: str, key: str) -> str:
    match = re.search(rf"^- {re.escape(key)}:\s+`(?P<value>.*)`\s*$", body, re.M)
    return match.group("value") if match else ""


def _extract_reason_keys(body: str) -> list[str]:
    raw = _extract_backtick_bullet(body, "agent_review_reason_keys").strip()
    if not raw:
        raw = _extract_backtick_bullet(body, "agent_review_reason_codes").strip()
    if not raw:
        return []
    return [part.strip() for part in raw.split(",") if part.strip()]


def _extract_reason_messages(body: str) -> list[str]:
    match = re.search(
        r"^- agent_review_reason_messages:\s*\n(?P<items>(?:  - `.*?`\n?)*)",
        body,
        re.M | re.S,
    )
    if match:
        items = re.findall(r"^  - `(?P<value>.*)`\s*$", match.group("items"), re.M)
        if items != [""]:
            return [item for item in items if item]
    legacy_summary = _extract_backtick_bullet(body, "agent_review_reason_summary").strip()
    return [legacy_summary] if legacy_summary else []


def load_existing_review_states(path: Path) -> dict[tuple[int, int], ExistingReviewState]:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    states: dict[tuple[int, int], ExistingReviewState] = {}
    for match in PROMPT_ENTRY_RE.finditer(text):
        body = match.group("body")
        key = (int(match.group("scene_id")), int(match.group("cut_id")))
        states[key] = ExistingReviewState(
            agent_review_ok=_extract_bool_bullet(body, "agent_review_ok", True),
            human_review_ok=_extract_bool_bullet(body, "human_review_ok", False),
            agent_review_reason_keys=_extract_reason_keys(body),
            agent_review_reason_messages=_extract_reason_messages(body),
        )
    return states


def render_collection(data: dict, *, mode_filter: str, existing_states: dict[tuple[int, int], ExistingReviewState] | None = None) -> str:
    lines = [
        "# Image Prompt Collection",
        "",
        f"抽出対象: `still_image_plan.mode == {mode_filter}`",
        "",
    ]
    count = 0
    for scene in data.get("scenes", []):
        sid = scene.get("scene_id")
        if "cuts" not in scene or not isinstance(sid, int) or sid <= 0:
            continue
        for cut in scene["cuts"]:
            plan = cut.get("still_image_plan") or {}
            if str(plan.get("mode") or "") != mode_filter:
                continue
            count += 1
            cid = cut.get("cut_id")
            existing = (existing_states or {}).get(
                (sid, cid),
                ExistingReviewState(
                    agent_review_ok=True,
                    human_review_ok=False,
                    agent_review_reason_keys=[],
                    agent_review_reason_messages=[],
                ),
            )
            image_generation = cut.get("image_generation") or {}
            narration = ((cut.get("audio") or {}).get("narration") or {}).get("text", "")
            lines.extend(
                [
                    f"## scene{sid:02d}_cut{cid:02d}",
                    "",
                    f"- output: `{image_generation.get('output', '')}`",
                    f"- narration: `{narration}`" if narration else "- narration: `(silent)`",
                    f"- rationale: `{plan.get('rationale', '')}`",
                    f"- agent_review_ok: `{'true' if existing.agent_review_ok else 'false'}`",
                    f"- human_review_ok: `{'true' if existing.human_review_ok else 'false'}`",
                    (
                        f"- agent_review_reason_keys: `{', '.join(existing.agent_review_reason_keys)}`"
                        if existing.agent_review_reason_keys
                        else "- agent_review_reason_keys: ``"
                    ),
                    "- agent_review_reason_messages:",
                ]
            )
            if existing.agent_review_reason_messages:
                lines.extend(f"  - `{message}`" for message in existing.agent_review_reason_messages)
            else:
                lines.append("  - ``")
            lines.extend(
                [
                    "",
                    "```text",
                    str(image_generation.get("prompt", "")).rstrip(),
                    "```",
                    "",
                ]
            )
    lines.insert(3, f"件数: `{count}`")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export image prompt collection from a manifest.")
    parser.add_argument("--manifest", required=True, help="Path to video_manifest.md")
    parser.add_argument("--out", default=None, help="Output markdown path (default: <manifest_dir>/image_prompt_collection.md)")
    parser.add_argument("--mode", default="generate_still", help="still_image_plan.mode filter (default: generate_still)")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    out_path = Path(args.out) if args.out else manifest_path.with_name("image_prompt_collection.md")
    data = load_manifest_yaml(manifest_path)
    existing_states = load_existing_review_states(out_path)
    out_path.write_text(render_collection(data, mode_filter=args.mode, existing_states=existing_states), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
