#!/usr/bin/env python3
"""Author a rich research-grounded story.md with Codex app-server."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
from pathlib import Path
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.codex_app_server import create_codex_app_server_client  # noqa: E402
from toc.harness import load_structured_document  # noqa: E402
from toc.story_author_pipeline import author_story_from_research, StoryAuthorCacheMiss  # noqa: E402
from toc.production_repair import handoff_prompt, RepairSession
from toc.story_syntax_patch import SYNTAX_REPAIR_CONTRACT, SYNTAX_EDIT_SCHEMA, SyntaxPatchError, apply_syntax_edits, build_syntax_prompt, syntax_patchable
from toc.story_author_runtime import (  # noqa: E402
    DEFAULT_REPAIR_AUTHOR_MODEL,
    DEFAULT_STORY_AUTHOR_MODEL,
    DEFAULT_SCENE_AUTHOR_MODEL,
    STORY_AUTHOR_TRANSPORT_SCHEMA,
    StoryAuthorRuntimeError,
    build_story_transport_prompt,
    decode_story_transport_payload,
    run_structured_story_turn,
)


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _model_for_role(args: argparse.Namespace, role: str) -> str:
    models = {
        "architect": args.model,
        "scene_author": args.scene_author_model,
        "repair": args.repair_author_model,
        "field_repair": args.repair_author_model,
    }
    try:
        return str(models[role])
    except KeyError as exc:
        raise RuntimeError(f"unsupported story author role: {role}") from exc


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    research_path = args.research.resolve()
    output_path = args.output.resolve()
    run_dir = output_path.parent
    _research_text, research = load_structured_document(research_path)
    if not isinstance(research, dict) or not research:
        raise RuntimeError("research.md must contain a non-empty structured document")

    log_root = run_dir / "logs/authoring/story"
    prompt_root = log_root / "prompts"
    output_root = log_root / "outputs"
    prompt_root.mkdir(parents=True, exist_ok=True)
    output_root.mkdir(parents=True, exist_ok=True)
    call_number = 0
    pending_cache_probe = None
    provenance_records: list[dict[str, Any]] = []

    async def turn_runner(**kwargs: Any) -> dict[str, Any]:
        nonlocal call_number, pending_cache_probe
        cache_only = bool(kwargs.get('cache_only', False))
        ordinal = call_number + 1
        if not cache_only:
            pending_cache_probe = None
            call_number = ordinal
        role = str(kwargs["role"])
        prompt = str(kwargs["prompt"])
        output_schema = dict(kwargs["output_schema"])
        direct_output = role == 'field_repair'
        transport_schema = output_schema if direct_output else STORY_AUTHOR_TRANSPORT_SCHEMA
        transport_prompt = (prompt if direct_output else build_story_transport_prompt(prompt, output_schema) + handoff_prompt(run_dir, 'p220'))
        turn_model = _model_for_role(args, role)
        plans = kwargs.get('scene_plans') or []
        item_id = str(kwargs.get('scene_id') or (kwargs.get('scene_plan') or {}).get('scene_id')
            or (plans[0].get('scene_id') if len(plans) == 1 else '') or 'whole_story')
        filename_id = re.sub(r"[^A-Za-z0-9_.-]", "_", item_id).strip("._")[:80] or "item"
        stem = f"{ordinal:03d}_{role}_{filename_id}"
        _atomic_write_text(prompt_root / f"{stem}.md", transport_prompt)
        cached_output_path = output_root / f"{stem}.json"
        cached_provenance_path = output_root / f"{stem}.provenance.json"
        transport_prompt_sha256 = hashlib.sha256(
            transport_prompt.encode("utf-8")
        ).hexdigest()
        schema_sha256 = hashlib.sha256(json.dumps(transport_schema, ensure_ascii=False,
            sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        legacy_stem = f"{ordinal:03d}_{role}_{'item' if role == 'scene_author' else 'whole_story'}"
        cache_paths = [(cached_output_path, cached_provenance_path)]
        if not direct_output and legacy_stem != stem:
            cache_paths.append((output_root / f'{legacy_stem}.json', output_root / f'{legacy_stem}.provenance.json'))
        for cache_output, cache_provenance in ([] if kwargs.get('bypass_cache', False) else cache_paths):
            if not cache_output.is_file() or not cache_provenance.is_file():
                continue
            try:
                stored = json.loads(cache_provenance.read_text(encoding='utf-8'))
                cached_payload = json.loads(cache_output.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            if (
                isinstance(stored, dict) and isinstance(cached_payload, dict)
                and stored.get('author_prompt_sha256', stored.get('prompt_sha256')) == transport_prompt_sha256
                and stored.get('author_schema_sha256', stored.get('output_schema_sha256')) == schema_sha256
                and stored.get('model') == turn_model
                and (not (stored.get('syntax_repairs') or stored.get('syntax_patch_provenance')) or (
                    stored.get('syntax_repair_contract') == SYNTAX_REPAIR_CONTRACT
                    and stored.get('syntax_repair_model') == args.repair_author_model
                ))
                and stored.get('decoded_payload_sha256') == hashlib.sha256(_canonical_json(cached_payload).encode()).hexdigest()
            ):
                if cache_only:
                    pending_cache_probe = (ordinal, stored, cached_payload)
                else:
                    provenance_records.append({**stored, 'cache_reused': True})
                return cached_payload
        if cache_only:
            raise StoryAuthorCacheMiss(f'No cached {role} response for {item_id}')

        def client_factory():
            return create_codex_app_server_client(
                cwd=run_dir,
                scrub_sensitive_env=True,
                require_chatgpt_account=True,
                require_chatgpt_pro=True,
            )

        receipts = []
        syntax_provenance = []
        result = await run_structured_story_turn(
            client_factory=client_factory, cwd=run_dir, prompt=transport_prompt,
            output_schema=transport_schema, model=turn_model, timeout_seconds=args.timeout_seconds,
            allow_multiple_completed_messages=True,
        )
        if direct_output:
            payload = result.payload
        else:
            try:
                payload = decode_story_transport_payload(result.payload, on_syntax_repair=lambda receipt: receipts.append(receipt.as_dict()))
            except StoryAuthorRuntimeError as exc:
                raw = result.payload.get('result_json')
                if not isinstance(raw, str) or not syntax_patchable(raw) or (getattr(exc, 'diagnostics', None) or {}).get('code') != 'invalid_json':
                    raise
                cause = exc.__cause__
                diagnostics = getattr(exc, 'diagnostics', None) or {
                    'message': str(exc), 'offset': getattr(cause, 'pos', None),
                    'line': getattr(cause, 'lineno', None), 'column': getattr(cause, 'colno', None),
                }
                syntax_session = RepairSession(run_dir, 'p220', binding={'syntax_input': hashlib.sha256(raw.encode()).hexdigest()},
                    stage_limit=args.max_repair_rounds)
                syntax_unit = f'syntax-{role}-{item_id}'
                previous_patch, patch_error = None, None
                while True:
                    syntax_session.feedback(syntax_unit, {'raw_json': raw, 'previous_patch': previous_patch},
                        [f'JSON syntax only: {patch_error or diagnostics}'])
                    syntax_session.claim(syntax_unit)
                    syntax_prompt = build_syntax_prompt(raw, diagnostics, previous_patch, patch_error)
                    syntax_result = await run_structured_story_turn(
                        client_factory=client_factory, cwd=run_dir, prompt=syntax_prompt,
                        output_schema=SYNTAX_EDIT_SCHEMA, model=args.repair_author_model,
                        timeout_seconds=args.timeout_seconds, allow_multiple_completed_messages=True,
                    )
                    syntax_provenance.append(syntax_result.provenance.as_dict())
                    previous_patch = syntax_result.payload
                    try:
                        fixed = apply_syntax_edits(raw, previous_patch)
                    except SyntaxPatchError as error:
                        patch_error = str(error)
                        continue
                    payload = decode_story_transport_payload({'result_json': fixed}, on_syntax_repair=lambda receipt: receipts.append(receipt.as_dict()))
                    receipts.append({'mode': 'syntax_patch', 'edits': previous_patch['edits'],
                        'before_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                        'after_sha256': hashlib.sha256(fixed.encode()).hexdigest()})
                    syntax_session.complete(syntax_unit)
                    break
        if not isinstance(payload, dict):
            raise RuntimeError('story author must return an object')
        _atomic_write_text(cached_output_path, _canonical_json(payload))
        if receipts:
            _atomic_write_text(output_root / f'{stem}.syntax.json', _canonical_json({
                'original_payload': result.payload, 'repairs': receipts, 'syntax_patch_provenance': syntax_provenance,
            }))
        provenance = {
            "role": role,
            "item_id": item_id,
            **result.provenance.as_dict(),
            "author_prompt_sha256": transport_prompt_sha256,
            "author_schema_sha256": schema_sha256,
            "output_mode": "direct_patch" if direct_output else "result_json",
            "syntax_repair_contract": SYNTAX_REPAIR_CONTRACT,
            "syntax_repair_model": args.repair_author_model,
            "syntax_repairs": receipts,
            "syntax_patch_provenance": syntax_provenance,
            "decoded_payload_sha256": hashlib.sha256(
                _canonical_json(payload).encode("utf-8")
            ).hexdigest(),
        }
        provenance_records.append(provenance)
        _atomic_write_text(
            cached_provenance_path,
            _canonical_json(provenance),
        )
        return payload

    def commit_cache_hit(response):
        nonlocal call_number, pending_cache_probe
        if pending_cache_probe is None:
            raise RuntimeError('no pending cache probe to commit')
        ordinal, stored, cached_payload = pending_cache_probe
        if ordinal != call_number + 1 or cached_payload != response:
            raise RuntimeError('cache probe changed before acceptance')
        call_number = ordinal
        provenance_records.append({**stored, 'cache_reused': True})
        pending_cache_probe = None

    turn_runner.supports_cache_lookup = True
    turn_runner.commit_cache_hit = commit_cache_hit
    input_sha256 = hashlib.sha256(research_path.read_bytes()).hexdigest()
    _atomic_write_text(
        log_root / "input.json",
        _canonical_json(
            {
                "schema_version": "story_author_input_v1",
                "topic": args.topic,
                "target_duration_seconds": args.target_duration_seconds,
                "research_path": str(research_path),
                "research_sha256": input_sha256,
                "model": args.model,
                "scene_author_model": args.scene_author_model,
                "repair_author_model": args.repair_author_model,
                "research": research,
            }
        ),
    )
    started = time.monotonic()
    result = await author_story_from_research(
        research,
        topic=args.topic,
        target_duration_seconds=args.target_duration_seconds,
        turn_runner=turn_runner,
        max_repair_rounds=args.max_repair_rounds,
        source_research=str(research_path),
        output_path=output_path,
    )
    validation = {
        "schema_version": "story_author_validation_v1",
        "status": "passed",
        "validation_errors": list(result.validation_errors),
        "source_digest": result.source_digest,
        "model": args.model,
        "scene_author_model": args.scene_author_model,
        "repair_author_model": args.repair_author_model,
        "turn_count": call_number,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "output_path": str(output_path),
        "provenance": provenance_records,
    }
    _atomic_write_text(
        log_root / "validation.json",
        _canonical_json(validation),
    )
    return validation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--topic", required=True)
    parser.add_argument(
        "--target-duration-seconds",
        type=int,
        default=300,
    )
    parser.add_argument(
        "--model",
        default=(
            os.environ.get("TOC_STORY_AUTHOR_MODEL", "").strip()
            or DEFAULT_STORY_AUTHOR_MODEL
        ),
    )
    parser.add_argument(
        "--scene-author-model",
        default=(
            os.environ.get("TOC_SCENE_AUTHOR_MODEL", "").strip()
            or DEFAULT_SCENE_AUTHOR_MODEL
        ),
    )
    parser.add_argument(
        "--repair-author-model",
        default=(
            os.environ.get("TOC_REPAIR_AUTHOR_MODEL", "").strip()
            or DEFAULT_REPAIR_AUTHOR_MODEL
        ),
    )
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-repair-rounds", type=int, default=12)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
