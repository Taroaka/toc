#!/usr/bin/env python3
"""Author a rich research-grounded story.md with Codex app-server."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.codex_app_server import create_codex_app_server_client  # noqa: E402
from toc.harness import load_structured_document  # noqa: E402
from toc.story_author_pipeline import author_story_from_research  # noqa: E402
from toc.story_author_runtime import (  # noqa: E402
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
    provenance_records: list[dict[str, Any]] = []

    async def turn_runner(**kwargs: Any) -> dict[str, Any]:
        nonlocal call_number
        call_number += 1
        role = str(kwargs["role"])
        prompt = str(kwargs["prompt"])
        output_schema = dict(kwargs["output_schema"])
        transport_prompt = build_story_transport_prompt(prompt, output_schema)
        turn_model = (
            args.model if role == "architect" else args.scene_author_model
        )
        item_id = (
            str((kwargs.get("scene_plan") or {}).get("scene_id") or "")
            if role == "scene_author"
            else "whole_story"
        )
        stem = f"{call_number:03d}_{role}_{item_id or 'item'}"
        _atomic_write_text(prompt_root / f"{stem}.md", transport_prompt)
        cached_output_path = output_root / f"{stem}.json"
        cached_provenance_path = output_root / f"{stem}.provenance.json"
        transport_prompt_sha256 = hashlib.sha256(
            transport_prompt.encode("utf-8")
        ).hexdigest()
        if cached_output_path.is_file() and cached_provenance_path.is_file():
            try:
                cached_provenance = json.loads(
                    cached_provenance_path.read_text(encoding="utf-8")
                )
                cached_payload = json.loads(
                    cached_output_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                cached_provenance = {}
                cached_payload = None
            if (
                isinstance(cached_provenance, dict)
                and cached_provenance.get("prompt_sha256")
                == transport_prompt_sha256
                and cached_provenance.get("model") == turn_model
                and isinstance(cached_payload, dict)
            ):
                provenance_records.append(
                    {**cached_provenance, "cache_reused": True}
                )
                return cached_payload

        def client_factory():
            return create_codex_app_server_client(
                cwd=run_dir,
                scrub_sensitive_env=True,
                require_chatgpt_account=True,
                require_chatgpt_pro=True,
            )

        result = None
        payload = None
        for transport_attempt in range(1, 3):
            result = await run_structured_story_turn(
                client_factory=client_factory,
                cwd=run_dir,
                prompt=transport_prompt,
                output_schema=STORY_AUTHOR_TRANSPORT_SCHEMA,
                model=turn_model,
                timeout_seconds=args.timeout_seconds,
                allow_multiple_completed_messages=True,
            )
            try:
                payload = decode_story_transport_payload(result.payload)
            except StoryAuthorRuntimeError:
                if transport_attempt >= 2:
                    raise
                continue
            break
        if result is None or payload is None:
            raise RuntimeError("story author transport produced no decodable payload")
        _atomic_write_text(cached_output_path, _canonical_json(payload))
        provenance = {
            "role": role,
            "item_id": item_id,
            **result.provenance.as_dict(),
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
    parser.add_argument("--timeout-seconds", type=int, default=600)
    parser.add_argument("--max-repair-rounds", type=int, default=12)
    return parser


def main() -> None:
    args = _parser().parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
