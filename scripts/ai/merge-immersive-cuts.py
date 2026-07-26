#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import sys
import unicodedata
from pathlib import Path

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.immersive_manifest import (
    is_character_reference_scene,
    scene_numeric_id,
    story_scene_ids,
)


CANONICAL_SEMANTIC_KEYS = frozenset(
    {
        "scene_event",
        "scene_cut_coverage_plan",
        "cut_contract",
        "source_event_contract",
        "event_context_for_cut",
        "first_frame_visual_plan",
        "drawable_prompt_ir",
    }
)
PROVIDER_CONTROLLED_KEYS = frozenset(
    {
        "api_prompt_payload",
        "applied_request_ids",
        "backend",
        "candidates",
        "compiler_version",
        "debug_prompt_source",
        "destination",
        "execution_options",
        "generation",
        "generation_job_id",
        "image_generation_item_id",
        "implementation_trace",
        "model",
        "negative_prompt",
        "policy_version",
        "prompt_authoring_context",
        "prompt_policy_version",
        "prompt_sha256",
        "provider",
        "provider_policy",
        "provider_prompt_payload",
        "provider_request_binding",
        "reference_content_sha256",
        "reference_images",
        "reference_instructions",
        "reference_sha256",
        "reference_sha256s",
        "request_digest",
        "request_revision",
        "savedPath",
        "selected",
        "sha256",
        "source_digest",
        "turn_id",
    }
)
PROVIDER_CONTROLLED_KEYS_LOWER = frozenset(
    key.lower() for key in PROVIDER_CONTROLLED_KEYS
)
REVIEW_CONTROLLED_KEYS = frozenset(
    {
        "approval",
        "approval_status",
        "approved",
        "approved_revision",
        "projection_review_contract",
        "review",
        "review_revision",
        "review_status",
        "status",
    }
)

SCRATCH_ROOT_KEYS = frozenset({"scene_id", "cuts"})
SCRATCH_CUT_KEYS = frozenset({"cut_id", "image_generation", "audio"})
SCRATCH_IMAGE_GENERATION_KEYS = frozenset(
    {
        "tool",
        "character_ids",
        "object_ids",
        "prompt",
        "output",
        "aspect_ratio",
        "image_size",
        "references",
    }
)
SCRATCH_AUDIO_KEYS = frozenset({"narration"})
SCRATCH_NARRATION_KEYS = frozenset(
    {"tool", "text", "output", "normalize_to_scene_duration"}
)
IMAGE_OUTPUT_ROOT = ("assets", "scenes")
IMAGE_OUTPUT_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})
NARRATION_OUTPUT_ROOT = ("assets", "audio")
NARRATION_OUTPUT_SUFFIXES = frozenset({".mp3", ".wav", ".m4a", ".aac", ".ogg"})
CANONICAL_ROUTE_HINT = (
    "Use the canonical p400/create route: /api/image-gen/runs/create or "
    "python scripts/toc-create-run-headless.py."
)


class ScratchValidationError(ValueError):
    pass


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
        state_path.write_text(
            state_path.read_text(encoding="utf-8") + block, encoding="utf-8"
        )
        return
    state_path.write_text(block, encoding="utf-8")


def _canonical_semantic_paths(value: object, *, path: str = "$manifest") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in CANONICAL_SEMANTIC_KEYS:
                found.append(child_path)
            found.extend(_canonical_semantic_paths(child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_canonical_semantic_paths(child, path=f"{path}[{index}]"))
    return found


def _assert_legacy_manifest_allowed(manifest: dict, *, explicit_opt_in: bool) -> None:
    canonical_paths = _canonical_semantic_paths(manifest)
    if canonical_paths:
        markers = ", ".join(canonical_paths[:4])
        suffix = " ..." if len(canonical_paths) > 4 else ""
        raise SystemExit(
            "Canonical semantic manifest detected "
            f"({markers}{suffix}). This legacy raw-prompt merge cannot preserve "
            f"semantic cut projection or review contracts. {CANONICAL_ROUTE_HINT}"
        )
    if not explicit_opt_in:
        raise SystemExit(
            "This command is a legacy fixed-cut raw-prompt merge. Re-run with "
            "--legacy-fixed-cut-scaffold only for a non-canonical legacy manifest. "
            f"{CANONICAL_ROUTE_HINT}"
        )


def _scratch_error(path: Path, reason: str) -> ScratchValidationError:
    return ScratchValidationError(f"Invalid scratch {path.name}: {reason}")


def _scratch_field_category(key: str) -> str | None:
    if key in CANONICAL_SEMANTIC_KEYS:
        return "canonical"
    lower_key = key.lower()
    if (
        lower_key in PROVIDER_CONTROLLED_KEYS_LOWER
        or lower_key.endswith(("_sha256", "_digest", "_revision"))
        or lower_key == "provider"
        or lower_key.startswith("provider_")
    ):
        return "provider"
    if (
        key in REVIEW_CONTROLLED_KEYS
        or "review" in lower_key
        or "approval" in lower_key
        or lower_key.startswith("approved")
    ):
        return "review"
    return None


def _forbidden_scratch_fields(value: object) -> list[tuple[str, str]]:
    """Find control-plane keys anywhere in scratch, including inside list values."""
    found: list[tuple[str, str]] = []
    pending: list[tuple[object, str]] = [(value, "$scratch")]
    seen_containers: set[int] = set()
    while pending:
        current, current_path = pending.pop()
        if not isinstance(current, (dict, list)):
            continue
        identity = id(current)
        if identity in seen_containers:
            continue
        seen_containers.add(identity)
        if isinstance(current, dict):
            children: list[tuple[object, str]] = []
            for raw_key, child in current.items():
                key = str(raw_key)
                child_path = f"{current_path}.{key}"
                category = _scratch_field_category(key)
                if category is not None:
                    found.append((child_path, category))
                children.append((child, child_path))
            pending.extend(reversed(children))
        else:
            pending.extend(
                (child, f"{current_path}[{index}]")
                for index, child in reversed(tuple(enumerate(current)))
            )
    return found


def _assert_no_forbidden_scratch_fields(path: Path, value: object) -> None:
    forbidden = _forbidden_scratch_fields(value)
    if not forbidden:
        return
    markers = ", ".join(
        f"{field_path} ({category})" for field_path, category in forbidden[:6]
    )
    suffix = " ..." if len(forbidden) > 6 else ""
    raise _scratch_error(
        path,
        f"forbidden canonical/provider/review field(s): {markers}{suffix}. "
        "Legacy scratch may contain only the fixed raw-prompt schema.",
    )


def _assert_allowed_keys(
    path: Path,
    value: dict,
    *,
    allowed: frozenset[str],
    field_path: str,
) -> None:
    unknown_paths = [
        f"{field_path}.{key}"
        for key in value
        if not isinstance(key, str) or key not in allowed
    ]
    if unknown_paths:
        markers = ", ".join(unknown_paths[:6])
        suffix = " ..." if len(unknown_paths) > 6 else ""
        raise _scratch_error(
            path,
            f"unknown field(s) outside the legacy allowlist: {markers}{suffix}",
        )


def _validated_string_list(path: Path, value: object, *, field_path: str) -> list[str]:
    if not isinstance(value, list):
        raise _scratch_error(path, f"{field_path} must be a list")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise _scratch_error(
                path,
                f"{field_path}[{index}] must be a non-empty string",
            )
        normalized.append(item)
    return normalized


def _normalize_run_relative_output_path(
    path: Path,
    *,
    run_dir: Path,
    value: str,
    field_path: str,
    required_root: tuple[str, ...],
    allowed_suffixes: frozenset[str],
    media_label: str,
) -> str:
    raw = value.strip()
    portable = raw.replace("\\", "/")
    if any(char in raw for char in ("\x00", "\r", "\n", "`")):
        raise _scratch_error(
            path,
            f"{field_path} must be a safe run-relative path without control characters",
        )
    try:
        candidate = Path(portable)
    except (OSError, ValueError) as exc:
        raise _scratch_error(
            path,
            f"{field_path} must be a safe run-relative path",
        ) from exc
    invalid_absolute = (
        candidate.is_absolute()
        or portable.startswith("//")
        or bool(re.match(r"^[A-Za-z]:", portable))
    )
    if invalid_absolute:
        raise _scratch_error(path, f"{field_path} must be a run-relative path")
    if ".." in candidate.parts:
        raise _scratch_error(
            path,
            f"{field_path} must be a run-relative path and must not contain '..'",
        )
    normalized_candidate = Path(
        *[part for part in candidate.parts if part not in {"", "."}]
    )
    if not normalized_candidate.parts:
        raise _scratch_error(path, f"{field_path} must identify a run-relative file")

    base = run_dir.resolve(strict=False)
    lexical = base
    for part in normalized_candidate.parts:
        lexical = lexical / part
        try:
            if lexical.is_symlink():
                raise _scratch_error(
                    path,
                    f"{field_path} must not traverse a symlink: {raw}",
                )
        except OSError as exc:
            raise _scratch_error(
                path,
                f"{field_path} could not be validated as a safe run-relative path",
            ) from exc
    try:
        resolved = lexical.resolve(strict=False)
        relative = resolved.relative_to(base)
    except (OSError, RuntimeError, ValueError) as exc:
        raise _scratch_error(
            path,
            f"{field_path} must be a run-relative path confined to the run directory",
        ) from exc
    if relative.as_posix() in {"", "."}:
        raise _scratch_error(path, f"{field_path} must identify a run-relative file")
    if relative.parts[: len(required_root)] != required_root:
        root_display = "/".join(required_root) + "/"
        raise _scratch_error(
            path,
            f"{field_path} must be a safe run-relative path under {root_display}",
        )
    if relative.suffix.lower() not in allowed_suffixes:
        suffix_display = ", ".join(sorted(allowed_suffixes))
        raise _scratch_error(
            path,
            f"{field_path} must identify a {media_label} file ({suffix_display})",
        )
    return relative.as_posix()


def _scratch_output_entries(cuts: list[dict]) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for cut in cuts:
        cut_id = int(cut["cut_id"])
        image_generation = cut["image_generation"]
        narration = cut["audio"]["narration"]
        entries.extend(
            (
                (
                    str(image_generation["output"]),
                    f"cut {cut_id} image_generation.output",
                ),
                (
                    str(narration["output"]),
                    f"cut {cut_id} audio.narration.output",
                ),
            )
        )
    return entries


def _output_collision_key(destination: str) -> str:
    return unicodedata.normalize("NFC", destination).casefold()


def _validate_cut_scene_file(
    path: Path,
    *,
    run_dir: Path,
    min_cuts: int | None,
    max_cuts: int | None,
    allow_todo_prompts: bool,
) -> tuple[int, list[dict]]:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise _scratch_error(path, f"invalid YAML ({exc})") from exc
    if not isinstance(data, dict):
        raise _scratch_error(path, "root must be a mapping")
    _assert_no_forbidden_scratch_fields(path, data)
    _assert_allowed_keys(
        path,
        data,
        allowed=SCRATCH_ROOT_KEYS,
        field_path="$scratch",
    )
    raw_scene_id = data.get("scene_id")
    if isinstance(raw_scene_id, bool) or not isinstance(raw_scene_id, int):
        raise _scratch_error(path, "scene_id must be an integer")
    scene_id = raw_scene_id
    filename_match = re.fullmatch(r"scene(\d+)\.yaml", path.name)
    if filename_match is None:
        raise _scratch_error(path, "filename must use scene<integer>.yaml")
    filename_scene_id = int(filename_match.group(1))
    if filename_scene_id != scene_id:
        raise _scratch_error(
            path,
            f"filename scene_id {filename_scene_id} does not match payload scene_id {scene_id}",
        )
    cuts = data.get("cuts")
    if not isinstance(cuts, list) or not cuts:
        raise _scratch_error(path, "cuts must be a non-empty list")
    if min_cuts is not None and len(cuts) < min_cuts:
        raise _scratch_error(
            path,
            f"contains {len(cuts)} cuts; explicit compatibility minimum {min_cuts} was requested",
        )
    if max_cuts is not None and len(cuts) > max_cuts:
        raise _scratch_error(
            path,
            f"contains {len(cuts)} cuts; explicit compatibility maximum {max_cuts} was requested",
        )

    normalized: list[dict] = []
    seen_cut_ids: set[int] = set()
    for idx, raw in enumerate(cuts, start=1):
        if not isinstance(raw, dict):
            raise _scratch_error(path, f"cuts[{idx - 1}] must be a mapping")
        cut_path = f"$scratch.cuts[{idx - 1}]"
        _assert_allowed_keys(
            path,
            raw,
            allowed=SCRATCH_CUT_KEYS,
            field_path=cut_path,
        )
        raw_cut_id = raw.get("cut_id")
        cut_id = idx if raw_cut_id is None else raw_cut_id
        if isinstance(cut_id, bool) or not isinstance(cut_id, int) or cut_id < 1:
            raise _scratch_error(
                path, f"cuts[{idx - 1}].cut_id must be a positive integer"
            )
        if cut_id in seen_cut_ids:
            raise _scratch_error(path, f"duplicate cut_id {cut_id}")
        seen_cut_ids.add(cut_id)
        ig = raw.get("image_generation")
        if not isinstance(ig, dict):
            raise _scratch_error(
                path, f"cut {cut_id} image_generation must be a mapping"
            )
        image_path = f"{cut_path}.image_generation"
        _assert_allowed_keys(
            path,
            ig,
            allowed=SCRATCH_IMAGE_GENERATION_KEYS,
            field_path=image_path,
        )
        prompt = ig.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            raise _scratch_error(
                path,
                f"cut {cut_id} image_generation.prompt must be a non-empty string",
            )
        if not allow_todo_prompts and "[TODO]" in prompt:
            raise _scratch_error(
                path,
                f"cut {cut_id} image_generation.prompt still contains [TODO]",
            )
        output = ig.get("output")
        if output is not None and not isinstance(output, str):
            raise _scratch_error(
                path,
                f"cut {cut_id} image_generation.output must be a string when provided",
            )
        if output is None or not output.strip():
            output = f"assets/scenes/scene{scene_id:02d}_cut{cut_id:02d}.png"
        normalized_image_output = _normalize_run_relative_output_path(
            path,
            run_dir=run_dir,
            value=output,
            field_path=f"cut {cut_id} image_generation.output",
            required_root=IMAGE_OUTPUT_ROOT,
            allowed_suffixes=IMAGE_OUTPUT_SUFFIXES,
            media_label="image",
        )
        normalized_ig: dict = {
            "prompt": prompt,
            "output": normalized_image_output,
        }
        if "tool" in ig:
            tool = ig["tool"]
            if not isinstance(tool, str) or not tool.strip():
                raise _scratch_error(
                    path,
                    f"cut {cut_id} image_generation.tool must be a non-empty string",
                )
            normalized_ig["tool"] = tool.strip()
        for list_key in ("character_ids", "object_ids", "references"):
            if list_key not in ig:
                normalized_ig[list_key] = []
            else:
                normalized_ig[list_key] = _validated_string_list(
                    path,
                    ig[list_key],
                    field_path=f"cut {cut_id} image_generation.{list_key}",
                )
        for string_key, default in (("aspect_ratio", "16:9"), ("image_size", "2K")):
            if string_key not in ig:
                normalized_ig[string_key] = default
            elif not isinstance(ig[string_key], str) or not ig[string_key].strip():
                raise _scratch_error(
                    path,
                    f"cut {cut_id} image_generation.{string_key} must be a non-empty string",
                )
            else:
                normalized_ig[string_key] = ig[string_key].strip()

        out_cut = {
            "cut_id": int(cut_id),
            "image_generation": normalized_ig,
        }

        # Ensure an audio anchor exists by default; p700 may map one narration span across multiple cuts.
        # Users can intentionally skip TTS at generation time via --skip-audio.
        audio = raw.get("audio")
        if audio is None:
            audio = {}
        elif not isinstance(audio, dict):
            raise _scratch_error(
                path, f"cut {cut_id} audio must be a mapping when provided"
            )
        _assert_allowed_keys(
            path,
            audio,
            allowed=SCRATCH_AUDIO_KEYS,
            field_path=f"{cut_path}.audio",
        )
        narration = audio.get("narration")
        if narration is None:
            narration = {}
        elif not isinstance(narration, dict):
            raise _scratch_error(
                path,
                f"cut {cut_id} audio.narration must be a mapping when provided",
            )
        _assert_allowed_keys(
            path,
            narration,
            allowed=SCRATCH_NARRATION_KEYS,
            field_path=f"{cut_path}.audio.narration",
        )
        normalized_narration: dict = {}
        tool = narration.get("tool")
        if tool is not None and not isinstance(tool, str):
            raise _scratch_error(
                path, f"cut {cut_id} audio.narration.tool must be a string"
            )
        if not isinstance(tool, str) or not tool.strip():
            normalized_narration["tool"] = "elevenlabs"
        else:
            normalized_narration["tool"] = tool.strip()
        # Do NOT inject placeholder narration text: this field is sent to TTS as-is.
        # Leave it empty so that missing narration is caught early (unless --skip-audio).
        if "text" not in narration:
            normalized_narration["text"] = ""
        elif not isinstance(narration["text"], str):
            raise _scratch_error(
                path, f"cut {cut_id} audio.narration.text must be a string"
            )
        else:
            normalized_narration["text"] = narration["text"]
        narration_output = narration.get("output")
        if narration_output is not None and not isinstance(narration_output, str):
            raise _scratch_error(
                path, f"cut {cut_id} audio.narration.output must be a string"
            )
        if not isinstance(narration_output, str) or not narration_output.strip():
            narration_output = (
                f"assets/audio/scene{scene_id:02d}_cut{cut_id:02d}_narration.mp3"
            )
        normalized_narration["output"] = _normalize_run_relative_output_path(
            path,
            run_dir=run_dir,
            value=narration_output,
            field_path=f"cut {cut_id} audio.narration.output",
            required_root=NARRATION_OUTPUT_ROOT,
            allowed_suffixes=NARRATION_OUTPUT_SUFFIXES,
            media_label="audio",
        )
        if "normalize_to_scene_duration" not in narration:
            normalized_narration["normalize_to_scene_duration"] = False
        elif not isinstance(narration["normalize_to_scene_duration"], bool):
            raise _scratch_error(
                path,
                f"cut {cut_id} audio.narration.normalize_to_scene_duration must be boolean",
            )
        else:
            normalized_narration["normalize_to_scene_duration"] = narration[
                "normalize_to_scene_duration"
            ]
        out_cut["audio"] = {"narration": normalized_narration}

        normalized.append(out_cut)

    normalized.sort(key=lambda c: int(c["cut_id"]))
    return int(scene_id), normalized


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge legacy fixed-cut raw-prompt scratch files (non-canonical only)."
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Immersive run dir containing video_manifest.md and scratch/cuts/*.yaml",
    )
    parser.add_argument(
        "--legacy-fixed-cut-scaffold",
        action="store_true",
        help="Explicitly opt in to this non-canonical legacy raw-prompt workflow.",
    )
    parser.add_argument(
        "--min-cuts",
        type=int,
        default=None,
        help="Optional legacy compatibility minimum; omitted means no minimum beyond non-empty.",
    )
    parser.add_argument(
        "--max-cuts",
        type=int,
        default=None,
        help="Optional legacy compatibility maximum; omitted means no maximum.",
    )
    parser.add_argument(
        "--allow-todo-prompts",
        action="store_true",
        help='Allow merging scratch files that still contain "[TODO]" in prompts (NOT recommended).',
    )
    parser.add_argument(
        "--force", action="store_true", help="Overwrite scenes that already have cuts."
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create video_manifest.md.bak before writing.",
    )
    args = parser.parse_args()

    if args.min_cuts is not None and int(args.min_cuts) < 1:
        raise SystemExit(
            "--min-cuts must be a positive integer when explicitly provided."
        )
    if args.max_cuts is not None and int(args.max_cuts) < 1:
        raise SystemExit(
            "--max-cuts must be a positive integer when explicitly provided."
        )
    if (
        args.min_cuts is not None
        and args.max_cuts is not None
        and int(args.min_cuts) > int(args.max_cuts)
    ):
        raise SystemExit("--min-cuts cannot be greater than --max-cuts.")

    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "video_manifest.md"
    state_path = run_dir / "state.txt"
    backup = manifest_path.with_suffix(".md.bak")
    if manifest_path.is_symlink():
        raise SystemExit(f"Manifest must not be a symlink: {manifest_path}")
    if state_path.is_symlink():
        raise SystemExit(f"State file must not be a symlink: {state_path}")
    if not args.no_backup and backup.is_symlink():
        raise SystemExit(f"Manifest backup must not be a symlink: {backup}")
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")

    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    manifest = yaml.safe_load(y)
    if not isinstance(manifest, dict):
        raise SystemExit("Manifest YAML must be a mapping at the root.")
    _assert_legacy_manifest_allowed(
        manifest,
        explicit_opt_in=bool(args.legacy_fixed_cut_scaffold),
    )
    raw_scenes = manifest.get("scenes")
    if not isinstance(raw_scenes, list):
        raise SystemExit("Manifest YAML scenes must be a list.")

    scratch_dir = run_dir / "scratch" / "cuts"
    if not scratch_dir.exists():
        raise SystemExit(
            f"Scratch not found: {scratch_dir} (run toc-immersive-cuts-multiagent.py first)"
        )

    scratch_files = sorted(scratch_dir.glob("scene*.yaml"))
    if not scratch_files:
        raise SystemExit(f"No scratch files found in: {scratch_dir}")

    available_story_scene_ids = set(story_scene_ids(raw_scenes))
    cuts_by_scene: dict[int, list[dict]] = {}
    output_owners: dict[str, str] = {}
    for f in scratch_files:
        try:
            parsed = _validate_cut_scene_file(
                f,
                run_dir=run_dir,
                min_cuts=int(args.min_cuts) if args.min_cuts is not None else None,
                max_cuts=int(args.max_cuts) if args.max_cuts is not None else None,
                allow_todo_prompts=bool(args.allow_todo_prompts),
            )
        except ScratchValidationError as exc:
            raise SystemExit(str(exc)) from exc
        sid, cuts = parsed
        if sid not in available_story_scene_ids:
            raise SystemExit(
                f"Invalid scratch {f.name}: scene_id {sid} is not an active story scene in the manifest"
            )
        if sid in cuts_by_scene:
            raise SystemExit(
                f"Invalid scratch {f.name}: scene_id {sid} is duplicated by another scratch file"
            )
        for destination, field_name in _scratch_output_entries(cuts):
            owner = f"{f.name} {field_name}"
            collision_key = _output_collision_key(destination)
            previous_owner = output_owners.get(collision_key)
            if previous_owner is not None:
                raise SystemExit(
                    f"Invalid scratch {f.name}: duplicate output destination {destination!r} "
                    f"for {owner}; already used by {previous_owner}"
                )
            output_owners[collision_key] = owner
        cuts_by_scene[int(sid)] = cuts

    if not cuts_by_scene:
        raise SystemExit("No valid non-empty legacy scratch scenes were provided.")

    changed: list[int] = []
    for s in raw_scenes:
        if not isinstance(s, dict):
            continue
        if is_character_reference_scene(s):
            continue
        sid = scene_numeric_id(s)
        if sid is None:
            continue
        if sid not in cuts_by_scene:
            continue

        has_cuts = isinstance(s.get("cuts"), list) and bool(s.get("cuts"))
        if has_cuts and not args.force:
            continue

        s.pop("image_generation", None)
        s.pop("video_generation", None)
        s.pop("audio", None)
        s.pop("narration", None)
        s["cuts"] = cuts_by_scene[int(sid)]
        changed.append(int(sid))

    if not changed:
        print("No scenes changed (maybe already have cuts; try --force).")
        return

    new_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)

    if not args.no_backup:
        shutil.copy2(manifest_path, backup)

    manifest_path.write_text(replace_yaml_block(md, new_yaml), encoding="utf-8")

    if state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "runtime.stage": "immersive_cuts_merged",
                "immersive.cuts.merged_scenes": ",".join(
                    str(s) for s in sorted(changed)
                ),
                "next.command": f'scripts/toc-immersive-ride-generate.sh --run-dir "{run_dir}"',
            },
        )

    print("Merged scenes:", ",".join(str(s) for s in sorted(changed)))
    print("Updated manifest:", manifest_path)
    print("Next: please run:")
    print(f'  scripts/toc-immersive-ride-generate.sh --run-dir "{run_dir}"')


if __name__ == "__main__":
    main()
