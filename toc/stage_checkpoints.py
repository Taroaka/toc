"""Durable, byte-bound stage receipts. Callers own the run lease and validators."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Sequence

from toc.run_root_binding import require_bound_run_root

from scripts.world_walk_source import (
    directory_identity_nofollow,
    ensure_directory_relative_nofollow,
    read_regular_file_nofollow,
    write_regular_file_nofollow,
)


class StageCheckpoints:
    def __init__(self, run_dir: Path, configuration: dict[str, Any]):
        self.root = run_dir
        binding = require_bound_run_root(run_dir)
        self.identity = binding.identity if binding else directory_identity_nofollow(run_dir)
        self.configuration = configuration
        self.started: dict[str, dict[str, Any]] = {}

    def _path(self, stage: str) -> str:
        if not re.fullmatch(r'[a-z][a-z0-9_]*', stage):
            raise ValueError('invalid checkpoint stage')
        return f'logs/checkpoints/{stage}.json'

    def _hashes(self, paths: Sequence[str]) -> dict[str, str]:
        return {path: hashlib.sha256(read_regular_file_nofollow(
            self.root, path, expected_root_identity=self.identity,
        )).hexdigest() for path in paths}

    def _inputs(self, paths: Sequence[str]) -> dict[str, Any]:
        return {'configuration': self.configuration, 'inputs': self._hashes(paths)}

    def _write(self, stage: str, data: dict[str, Any]) -> None:
        path = self._path(stage)
        ensure_directory_relative_nofollow(self.root, 'logs/checkpoints', expected_root_identity=self.identity)
        write_regular_file_nofollow(destination_root=self.root, destination_relative=path,
            expected_destination_root_identity=self.identity,
            data=(json.dumps({'schema': 'toc.stage_checkpoint.v1', **data}, ensure_ascii=False, sort_keys=True) + '\n').encode())

    def reusable(self, stage: str, inputs: Sequence[str], outputs: Sequence[str]) -> bool:
        path = self._path(stage)
        try:
            receipt = json.loads(read_regular_file_nofollow(self.root, path, expected_root_identity=self.identity))
            return (isinstance(receipt, dict) and receipt.get('schema') == 'toc.stage_checkpoint.v1'
                and receipt.get('status') == 'completed'
                and receipt.get('binding') == self._inputs(inputs)
                and receipt.get('outputs') == self._hashes(outputs))
        except (FileNotFoundError, json.JSONDecodeError, UnicodeError):
            return False

    def start(self, stage: str, inputs: Sequence[str], outputs: Sequence[str]) -> None:
        binding = self._inputs(inputs)
        self._write(stage, {'status': 'running', 'binding': binding, 'expected_outputs': list(outputs)})
        self.started[stage] = binding

    def complete(self, stage: str, inputs: Sequence[str], outputs: Sequence[str]) -> None:
        binding = self._inputs(inputs)
        if stage in self.started and self.started[stage] != binding:
            raise RuntimeError(f'{stage} inputs changed during authoring')
        self._write(stage, {'status': 'completed', 'binding': binding, 'outputs': self._hashes(outputs)})
