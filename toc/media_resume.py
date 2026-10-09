"""Exact-request journals for already-authorized narration, video and render work.

The API owns the run lease. No candidate is selected or approved by this module.
"""
from __future__ import annotations
from contextvars import ContextVar
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from toc.run_root_binding import require_bound_run_root

from scripts.world_walk_source import (
    directory_identity_nofollow, ensure_directory_relative_nofollow,
    read_regular_file_nofollow, write_regular_file_nofollow,
)

ACTIVE_MEDIA_JOURNAL: ContextVar['MediaJournal | None'] = ContextVar('media_journal', default=None)
KINDS = {'narration', 'narration_bulk', 'video', 'video_bulk', 'render', 'narration_drafts', 'video_prompts', 'render_freeze', 'sound'}


def result_failed(value: Any) -> bool:
    if isinstance(value, dict):
        return (bool(value.get('error')) or value.get('status') in {'failed', 'partial_failure', 'stale', 'blocked'}
            or any(result_failed(value[k]) for k in ('item', 'results', 'candidates') if k in value))
    if isinstance(value, list):
        return any(result_failed(v) for v in value)
    return False


def output_paths(value: Any) -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        # Ignore progress/state snapshots, debug logs, and input request echoes.
        for key in ('path', 'finalOutput'):
            if isinstance(value.get(key), str) and value[key]:
                paths.add(value[key])
        for key in ('item', 'results', 'candidates'):
            if key in value:
                paths.update(output_paths(value[key]))
    elif isinstance(value, list):
        for entry in value:
            paths.update(output_paths(entry))
    return paths


class MediaJournal:
    def __init__(self, root: Path, data: dict[str, Any]):
        self.root = root
        binding = require_bound_run_root(root)
        self.identity = binding.identity if binding else directory_identity_nofollow(root)
        self.data = data
        self.id = data['operation_id']
        if not isinstance(self.id, str) or not re.fullmatch('[0-9a-f]{32}', self.id):
            raise ValueError('invalid media operation id')
        if data.get('kind') not in KINDS:
            raise ValueError('unsupported media operation')
        self.request = data['request']

    def _read(self, path: str) -> bytes:
        return read_regular_file_nofollow(self.root, path, expected_root_identity=self.identity)

    def _hashes(self, paths) -> dict[str, str]:
        return {path: hashlib.sha256(self._read(path)).hexdigest() for path in sorted(paths)}

    def _inputs(self) -> dict[str, str]:
        paths = []
        for path in ('video_manifest.md', 'script.md'):
            try:
                self._read(path)
                paths.append(path)
            except FileNotFoundError:
                pass
        # Bind caller-selected render clips and video reference bytes too.
        def collect(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    if key in {'first_reference', 'last_reference', 'video_path', 'narration_path', 'audio_path'} and item:
                        paths.append(item)
                    elif key == 'references' and isinstance(item, list):
                        paths.extend(item)
                    elif isinstance(item, (dict, list)):
                        collect(item)
            elif isinstance(value, list):
                for item in value:
                    collect(item)
        collect(self.request)
        paths.extend(self.data.get('extra_inputs', []))
        hashes = {}
        for path in sorted(set(paths)):
            try:
                hashes.update(self._hashes([path]))
            except FileNotFoundError:
                # Some render-unit requests intentionally ignore per-cut paths.
                # Keep absence bound; the canonical renderer validates actual inputs.
                hashes[path] = "missing"
        return hashes

    def bind_file(self, relative: str) -> None:
        self.verify_inputs()
        digest = self._hashes([relative])[relative]
        self.data.setdefault('extra_inputs', []).append(relative)
        self.data['inputs'][relative] = digest
        self.save()

    def save(self) -> None:
        ensure_directory_relative_nofollow(self.root, 'logs/media_operations', expected_root_identity=self.identity)
        write_regular_file_nofollow(destination_root=self.root,
            destination_relative=f'logs/media_operations/{self.id}.json',
            expected_destination_root_identity=self.identity,
            data=(json.dumps(self.data, ensure_ascii=False, sort_keys=True) + '\n').encode())

    @classmethod
    def create(cls, root: Path, kind: str, request: dict[str, Any]) -> 'MediaJournal':
        journal = cls(root, {'schema': 'toc.media_operation.v1', 'operation_id': uuid.uuid4().hex,
            'kind': kind, 'request': request, 'status': 'running', 'created_ns': time.time_ns(), 'items': {}})
        journal.data['inputs'] = journal._inputs()
        journal.save()
        return journal

    @classmethod
    def load(cls, root: Path, operation_id: str) -> 'MediaJournal':
        if not re.fullmatch('[0-9a-f]{32}', operation_id):
            raise ValueError('invalid media operation id')
        binding = require_bound_run_root(root)
        data = json.loads(read_regular_file_nofollow(root, f'logs/media_operations/{operation_id}.json',
            expected_root_identity=binding.identity if binding else None))
        if not isinstance(data, dict) or data.get('schema') != 'toc.media_operation.v1' or data.get('operation_id') != operation_id:
            raise ValueError('invalid media operation journal')
        return cls(root, data)

    @classmethod
    def latest_incomplete(cls, root: Path) -> 'MediaJournal | None':
        require_bound_run_root(root)
        directory = root / 'logs/media_operations'
        if directory.is_symlink():
            raise ValueError('unsafe media journal directory')
        journals = [cls.load(root, p.stem) for p in directory.glob('*.json')]
        if not journals:
            return None
        covered: set[str] = set()
        for journal in sorted(journals, key=lambda j: j.data['created_ns'], reverse=True):
            family = journal.data['kind'].removesuffix('_bulk')
            request = journal.request
            if family in {'narration', 'video', 'sound'}:
                items = request.get('items', [request])
                scopes = {f"{family}:{item.get('item_id', '*')}" for item in items}
            else:
                scopes = {f"{family}:{request.get('output', '*')}"}
            if journal.data['status'] == 'completed':
                covered.update(scopes)
            elif not scopes <= covered:
                return journal
        return None

    def verify_inputs(self) -> None:
        if self.data.get('input_conflict'):
            raise ValueError('media operation inputs changed; submit the current settings again')
        current = self._inputs()
        expected = dict(self.data['inputs'])
        mutable_match = True
        for path in ('video_manifest.md', 'script.md'):
            actual = current.pop(path, None)
            original = expected.pop(path, None)
            head = self.data.get('authored_heads', {}).get(path, original)
            pending = self.data.get('pending_writes', {}).get(path, {})
            allowed = {head, pending.get('next', head)}
            mutable_match = mutable_match and actual in allowed
        if expected != current or not mutable_match:
            raise ValueError('media operation inputs changed; submit the current settings again')

    def _record_input_drift(self) -> bool:
        try:
            self.verify_inputs()
            return False
        except (ValueError, FileNotFoundError):
            self.data['input_conflict'] = True
            self.save()
            return True

    def authorize_manifest_update(self, content: str | None, path: str = "video_manifest.md") -> None:
        if self._record_input_drift():
            raise ValueError('media operation inputs changed; refusing to overwrite current artifacts')
        digest = hashlib.sha256(content.encode()).hexdigest() if content is not None else None
        if path not in {'video_manifest.md', 'script.md'}:
            raise ValueError('unsupported authored media input')
        versions = self.data.setdefault('authored_versions', {}).setdefault(path, [])
        if digest not in versions:
            versions.append(digest)
        self.data.setdefault('pending_writes', {})[path] = {'next': digest}
        self.save()

    def confirm_manifest_update(self, path: str) -> None:
        self.verify_inputs()
        pending = self.data.get('pending_writes', {}).get(path)
        if pending is None:
            raise ValueError('missing authorized artifact publication')
        current = self._inputs().get(path)
        if current != pending['next']:
            raise ValueError('artifact publication bytes changed')
        self.data.setdefault('authored_heads', {})[path] = current
        del self.data['pending_writes'][path]
        self.save()

    def cached(self, key: str, request: dict[str, Any]) -> dict[str, Any] | None:
        item = self.data['items'].get(key, {})
        if item.get('status') != 'completed' or item.get('request') != request:
            return None
        try:
            if item.get('outputs') and item['outputs'] == self._hashes(item['outputs']):
                return item['result']
        except FileNotFoundError:
            pass
        return None

    def complete_item(self, key: str, request: dict[str, Any], result: dict[str, Any]) -> None:
        paths = output_paths(result)
        successful = bool(paths) and not result_failed(result)
        try:
            hashes = self._hashes(paths) if successful else {}
        except FileNotFoundError:
            successful, hashes = False, {}
        self.data['items'][key] = {'request': request, 'result': result,
            'status': 'completed' if successful else 'failed',
            'outputs': hashes}
        self._record_input_drift()
        self.save()

    def finish(self, success: bool) -> None:
        drifted = self._record_input_drift()
        self.data['status'] = 'completed' if success and not drifted else 'failed'
        self.save()
