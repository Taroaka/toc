"""Replay a completed author response only under its exact recorded request."""

import json
from pathlib import Path

from scripts.world_walk_source import directory_identity_nofollow, read_regular_file_nofollow
from toc.story_author_runtime import (
    StoryAuthorResult, StoryAuthorProvenance, StoryAuthorRuntimeError,
    _decode_agent_payload, _sha256_text, _sha256_json,
)


def replay_recorded_turn(run_dir, log_dir, *, prompt, schema, model, expected_identity=None):
    root = Path(run_dir)
    identity = directory_identity_nofollow(root)
    if expected_identity is not None and identity != expected_identity:
        raise ValueError('author response cache: run identity changed')
    if Path(log_dir).is_absolute() or '..' in Path(log_dir).parts:
        raise ValueError('author response cache: logs must belong to the run')
    root = root.resolve()
    folder = root / log_dir
    for path in sorted(folder.glob('*-provenance-*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        record = json.loads(read_regular_file_nofollow(root, path.relative_to(root), expected_root_identity=identity))
        if not isinstance(record, dict) or any(record.get(key) != value for key, value in {
            'schema_version': 'story_author_runtime_provenance_v1',
            'prompt_sha256': _sha256_text(prompt), 'output_schema_sha256': _sha256_json(schema),
            'model': model, 'cwd': str(root), 'sandbox': 'read-only', 'approval_policy': 'never',
        }.items()):
            continue
        for transcript_path in sorted(folder.glob('*-transcript-*.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            transcript = json.loads(read_regular_file_nofollow(root, transcript_path.relative_to(root), expected_root_identity=identity))
            if not isinstance(transcript, list) or _sha256_json(transcript) != record.get('transcript_sha256'):
                continue
            try:
                payload, response = _decode_agent_payload(transcript, allow_multiple_completed_messages=True)
            except StoryAuthorRuntimeError:
                continue
            if _sha256_json(payload) != record.get('payload_sha256') or _sha256_text(response) != record.get('response_sha256'):
                continue
            provenance = StoryAuthorProvenance(**record)
            return StoryAuthorResult(payload=payload, model=model, thread_id=record['thread_id'],
                prompt_sha256=record['prompt_sha256'], payload_sha256=record['payload_sha256'],
                response_sha256=record['response_sha256'], transcript_sha256=record['transcript_sha256'],
                provenance=provenance, transcript=tuple(transcript), response_text=response)
    return None
