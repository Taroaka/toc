#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.immersive_manifest import is_character_reference_scene, scene_numeric_id, story_scene_ids
from toc.script_narration import materialize_elevenlabs_tts_text, normalize_stability_profile, normalize_voice_tags


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return m.group(1)


def replace_yaml_block(text: str, new_yaml: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    start, end = m.span(1)
    return text[:start] + new_yaml.rstrip("\n") + text[end:]


def append_state_block(state_path: Path, kv: dict[str, str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in kv.items()]
    block = "\n".join(lines) + "\n---\n"
    if state_path.exists():
        state_path.write_text(state_path.read_text(encoding="utf-8") + block, encoding="utf-8")
        return
    state_path.write_text(block, encoding="utf-8")


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _load_scratch_file(path: Path) -> tuple[int, dict[int, dict[str, Any]]] | None:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    sid = _as_int(data.get("scene_id"))
    if sid is None:
        return None
    raw_cuts = data.get("cuts")
    if not isinstance(raw_cuts, list) or not raw_cuts:
        return None
    out: dict[int, dict[str, Any]] = {}
    for c in raw_cuts:
        if not isinstance(c, dict):
            continue
        cid = _as_int(c.get("cut_id"))
        if cid is None:
            continue
        out[int(cid)] = {
            "text": _as_str(c.get("narration_text")).strip(),
            "tts_text": _as_str(c.get("tts_text")).strip()
            or materialize_elevenlabs_tts_text(
                spoken_context=_as_str(c.get("spoken_context")).strip(),
                voice_tags=normalize_voice_tags(c.get("voice_tags")),
                spoken_body=_as_str(c.get("spoken_body")).strip(),
            ),
            "prompt": {
                "spoken_context": _as_str(c.get("spoken_context")).strip(),
                "voice_tags": normalize_voice_tags(c.get("voice_tags")),
                "spoken_body": _as_str(c.get("spoken_body")).strip(),
                "stability_profile": normalize_stability_profile(c.get("stability_profile")),
            },
            "contract": {
                "target_function": _as_str(c.get("target_function")).strip(),
                "must_cover": [str(v).strip() for v in list(c.get("must_cover") or []) if str(v).strip()],
                "must_avoid": [str(v).strip() for v in list(c.get("must_avoid") or []) if str(v).strip()],
                "done_when": [str(v).strip() for v in list(c.get("done_when") or []) if str(v).strip()],
            },
        }
    if not out:
        return int(sid), {}
    return int(sid), out


def _ensure_audio_narration(cut_or_scene: dict, *, scene_id: int, cut_id: int | None) -> dict:
    audio = cut_or_scene.get("audio")
    if not isinstance(audio, dict):
        audio = {}
        cut_or_scene["audio"] = audio
    narration = audio.get("narration")
    if not isinstance(narration, dict):
        narration = {}
        audio["narration"] = narration
    if "tool" not in narration or not str(narration.get("tool") or "").strip():
        narration["tool"] = "elevenlabs"
    if "output" not in narration or not str(narration.get("output") or "").strip():
        if cut_id is None:
            narration["output"] = f"assets/audio/scene{scene_id:02d}_narration.mp3"
        else:
            narration["output"] = f"assets/audio/scene{scene_id:02d}_cut{cut_id:02d}_narration.mp3"
    if "normalize_to_scene_duration" not in narration:
        narration["normalize_to_scene_duration"] = False
    if "text" not in narration:
        narration["text"] = ""
    if "tts_text" not in narration:
        narration["tts_text"] = ""
    return narration


def _normalize_contract(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "target_function": _as_str(raw.get("target_function")).strip(),
        "must_cover": [str(v).strip() for v in list(raw.get("must_cover") or []) if str(v).strip()],
        "must_avoid": [str(v).strip() for v in list(raw.get("must_avoid") or []) if str(v).strip()],
        "done_when": [str(v).strip() for v in list(raw.get("done_when") or []) if str(v).strip()],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge scratch/narration/sceneXX.yaml into immersive video_manifest.md (single-writer).")
    parser.add_argument("--run-dir", required=True, help="Immersive run dir containing video_manifest.md and scratch/narration/*.yaml")
    parser.add_argument("--force", action="store_true", help="Overwrite existing narration text even if non-empty.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create video_manifest.md.bak before writing.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    scratch_dir = run_dir / "scratch" / "narration"
    if not scratch_dir.exists():
        raise SystemExit(f"Scratch not found: {scratch_dir} (run toc-immersive-narration-multiagent.py first)")

    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")

    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    manifest = yaml.safe_load(y)
    if not isinstance(manifest, dict):
        raise SystemExit("Manifest YAML must be a mapping at the root.")
    raw_scenes = manifest.get("scenes")
    if not isinstance(raw_scenes, list):
        raise SystemExit("Manifest YAML scenes must be a list.")

    scratch_files = sorted(scratch_dir.glob("scene*.yaml"))
    if not scratch_files:
        raise SystemExit(f"No scratch files found in: {scratch_dir}")

    available_story_scene_ids = set(story_scene_ids(raw_scenes))
    by_scene: dict[int, dict[int, dict[str, Any]]] = {}
    for f in scratch_files:
        parsed = _load_scratch_file(f)
        if parsed is None:
            continue
        sid, cuts = parsed
        if sid not in available_story_scene_ids:
            continue
        by_scene[int(sid)] = cuts

    changed_scenes: list[int] = []
    for s in raw_scenes:
        if not isinstance(s, dict):
            continue
        if is_character_reference_scene(s):
            continue
        sid = scene_numeric_id(s)
        if sid is None or sid not in by_scene:
            continue

        raw_cuts = s.get("cuts")
        if isinstance(raw_cuts, list) and raw_cuts:
            wanted = by_scene[int(sid)]
            if not wanted:
                continue
            changed_any = False
            for cut in raw_cuts:
                if not isinstance(cut, dict):
                    continue
                cid = _as_int(cut.get("cut_id"))
                if cid is None or int(cid) not in wanted:
                    continue
                narration = _ensure_audio_narration(cut, scene_id=int(sid), cut_id=int(cid))
                prev = _as_str(narration.get("text")).strip()
                prev_tts = _as_str(narration.get("tts_text")).strip()
                payload = wanted[int(cid)]
                nxt = _as_str(payload.get("text")).strip()
                nxt_tts = _as_str(payload.get("tts_text")).strip()
                contract = _normalize_contract(payload.get("contract"))
                if prev and not args.force:
                    if prev_tts != nxt_tts and nxt_tts:
                        narration["tts_text"] = nxt_tts
                        changed_any = True
                    if contract != _normalize_contract(narration.get("contract") if isinstance(narration.get("contract"), dict) else {}):
                        narration["contract"] = contract
                        changed_any = True
                    continue
                if prev != nxt:
                    narration["text"] = nxt
                    changed_any = True
                if prev_tts != nxt_tts:
                    narration["tts_text"] = nxt_tts
                    changed_any = True
                if contract != _normalize_contract(narration.get("contract") if isinstance(narration.get("contract"), dict) else {}):
                    narration["contract"] = contract
                    changed_any = True
            if changed_any:
                changed_scenes.append(int(sid))
            continue

        # Scene-level narration (no cuts).
        wanted = by_scene[int(sid)]
        if not wanted:
            continue
        if len(wanted) != 1 or 1 not in wanted:
            raise SystemExit(f"scene{sid}: no cuts in manifest; scratch must have exactly one cut_id: 1")
        narration = _ensure_audio_narration(s, scene_id=int(sid), cut_id=None)
        prev = _as_str(narration.get("text")).strip()
        prev_tts = _as_str(narration.get("tts_text")).strip()
        payload = wanted[1]
        nxt = _as_str(payload.get("text")).strip()
        nxt_tts = _as_str(payload.get("tts_text")).strip()
        contract = _normalize_contract(payload.get("contract"))
        if prev and not args.force:
            if prev_tts != nxt_tts and nxt_tts:
                narration["tts_text"] = nxt_tts
                changed_scenes.append(int(sid))
            if contract != _normalize_contract(narration.get("contract") if isinstance(narration.get("contract"), dict) else {}):
                narration["contract"] = contract
                changed_scenes.append(int(sid))
            continue
        if prev != nxt:
            narration["text"] = nxt
            changed_scenes.append(int(sid))
        if prev_tts != nxt_tts:
            narration["tts_text"] = nxt_tts
            if int(sid) not in changed_scenes:
                changed_scenes.append(int(sid))
        if contract != _normalize_contract(narration.get("contract") if isinstance(narration.get("contract"), dict) else {}):
            narration["contract"] = contract
            if int(sid) not in changed_scenes:
                changed_scenes.append(int(sid))

    if not changed_scenes:
        print("No scenes changed.")
        return

    new_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    if not args.no_backup:
        backup = manifest_path.with_suffix(".md.bak")
        shutil.copy2(manifest_path, backup)
    manifest_path.write_text(replace_yaml_block(md, new_yaml), encoding="utf-8")

    state_path = run_dir / "state.txt"
    if state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "runtime.stage": "immersive_narration_merged",
                "immersive.narration.merged_scenes": ",".join(str(s) for s in sorted(set(changed_scenes))),
            },
        )

    print("Merged scenes:", ",".join(str(s) for s in sorted(set(changed_scenes))))
    print("Updated manifest:", manifest_path)


if __name__ == "__main__":
    main()
