"""Read the original request and classify early authoring continuation."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any
from scripts.world_walk_source import read_regular_file_nofollow
from toc.story_duration import normalize_target_duration
from toc.run_root_binding import require_bound_run_root


def read_create_input(run_dir: Path, *, expected_identity: tuple[int, int] | None = None) -> dict[str, Any]:
    binding = require_bound_run_root(run_dir)
    if binding is not None:
        if expected_identity is not None and expected_identity != binding.identity:
            raise ValueError("saved create input run identity mismatch")
        expected_identity = binding.identity
    data = json.loads(read_regular_file_nofollow(run_dir, 'logs/orchestration/create_input.json', expected_root_identity=expected_identity))
    if not isinstance(data, dict) or data.get('schema_version') != 'toc.create_input.v1':
        raise ValueError('missing or invalid saved create input; original request is required')
    for key in ('topic', 'source'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'invalid saved create input: {key}')
    if data.get('source_sha256') != hashlib.sha256(data['source'].encode()).hexdigest():
        raise ValueError('saved source digest mismatch')
    normalize_target_duration(data.get('target_duration_seconds'))
    if data.get('experience') not in {'cinematic_story', 'world_walk'}:
        raise ValueError('invalid saved experience')
    source_run = data.get('source_run')
    if data['experience'] == 'world_walk':
        if not isinstance(source_run, str) or not source_run.startswith('output/') or '..' in Path(source_run).parts:
            raise ValueError('invalid saved world-walk source run')
    elif source_run is not None:
        raise ValueError('unexpected saved source run')
    return data


def needs_authoring_resume(run_dir: Path) -> bool:
    """Missing upstream files require authoring, never an empty p500 reset."""
    from toc.p500_resume import PRESERVED_CANONICAL_FILES
    require_bound_run_root(run_dir)
    for relative in PRESERVED_CANONICAL_FILES:
        try:
            if not read_regular_file_nofollow(run_dir, relative).strip():
                return True
        except FileNotFoundError:
            return True
    saved = read_create_input(run_dir)
    from toc.stage_checkpoints import StageCheckpoints
    checkpoints = StageCheckpoints(run_dir, {
        "topic": saved["topic"], "source": saved["source"],
        "target_duration_seconds": saved["target_duration_seconds"],
        "experience": saved["experience"], "contract_version": 1,
    })
    from toc.p400_authoring import ARTIFACT
    stages = (
        ("research", [], ["research.md"]),
        ("story", ["research.md"], ["story.md"]),
        ("visual_value", ["research.md", "story.md"], ["visual_value.md"]),
        ("cinematic", ["research.md", "story.md", "visual_value.md"], [ARTIFACT]),
    )
    for stage, inputs, outputs in stages:
        try:
            read_regular_file_nofollow(run_dir, f"logs/checkpoints/{stage}.json")
        except FileNotFoundError:
            continue  # Legacy p400 runs remain subject to the p500 structural validators.
        if not checkpoints.reusable(stage, inputs, outputs):
            return True
    from toc.stage_evaluation.pipeline import check_manifest_single, check_script_single
    manifest_result, _ = check_manifest_single(run_dir, "standard", "immersive")
    script_result, _ = check_script_single(run_dir, "standard")
    return not manifest_result.get("passed", False) or not script_result.get("passed", False)
