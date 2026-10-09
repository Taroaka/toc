#!/usr/bin/env python3
"""Author p120 research from exact input and retrieved sources, never a story preset."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from server.codex_app_server import create_codex_app_server_client
from scripts.world_walk_source import directory_identity_nofollow, read_regular_file_nofollow
from toc.research_author import author_research
from toc.story_author_runtime import DEFAULT_STORY_AUTHOR_MODEL


class ResearchClient:
    """Enable retrieval through the existing shared app-server runtime."""
    def __init__(self, client):
        self.client = client

    async def start(self):
        await self.client.start()

    async def start_thread(self, **kwargs):
        return await self.client.start_thread(**kwargs, config={'web_search': 'live'})

    async def run_turn(self, **kwargs):
        return await self.client.run_turn(**kwargs)

    async def stop(self):
        await self.client.stop()


def prepare_grounding(run_dir: Path) -> str:
    subprocess.run([sys.executable, str(REPO_ROOT / 'scripts/prepare-stage-context.py'),
        '--stage', 'research', '--run-dir', str(run_dir), '--flow', 'immersive'],
        cwd=REPO_ROOT, check=True, capture_output=True, text=True)
    readset = json.loads(read_regular_file_nofollow(run_dir, 'logs/grounding/research.json'))
    if readset.get('missing_paths'):
        raise RuntimeError('research grounding inputs are missing')
    parts = []
    for group in ('global_doc', 'doc', 'template'):
        # The resolver owns the path inventory; fixed groups keep authoring read order.
        key = {'global_doc': 'global_docs', 'doc': 'docs', 'template': 'templates'}[group]
        for record in readset['resolved_paths'].get(key, []):
            path = Path(record['resolved_path']).resolve()
            path.relative_to(REPO_ROOT)
            parts.append(f"\n--- {record['path']} ---\n" + path.read_text(encoding='utf-8'))
    if not parts:
        raise RuntimeError('research grounding readset is empty')
    return '\n'.join(parts)


async def run(args):
    output = Path(os.path.abspath(args.output))
    if output.name != 'research.md':
        raise ValueError('research author output must be research.md')
    run_dir = output.parent
    directory_identity_nofollow(run_dir)
    source_path = Path(os.path.abspath(args.source_file))
    source = read_regular_file_nofollow(run_dir, source_path.relative_to(run_dir)).decode('utf-8')
    grounding = prepare_grounding(run_dir)
    def factory():
        return ResearchClient(create_codex_app_server_client(cwd=run_dir,
            scrub_sensitive_env=True, require_chatgpt_account=True, require_chatgpt_pro=True))
    await author_research(run_dir=run_dir, topic=args.topic, source=source,
        target_duration_seconds=args.target_duration_seconds, grounding=grounding,
        client_factory=factory, model=args.model, timeout_seconds=args.timeout_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topic', required=True)
    parser.add_argument('--source-file', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--target-duration-seconds', type=int, default=300)
    parser.add_argument('--model', default=os.environ.get('TOC_RESEARCH_AUTHOR_MODEL') or DEFAULT_STORY_AUTHOR_MODEL)
    parser.add_argument('--timeout-seconds', type=int, default=1200)
    args = parser.parse_args()
    asyncio.run(run(args))
    print(json.dumps({'status': 'published', 'output': str(args.output)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
