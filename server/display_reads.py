"""Read-only display acceleration; never used to authorize generation."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from threading import Lock
from typing import Any, Awaitable, Callable

import yaml

_cache: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
_cache_lock = Lock()
_pending: dict[tuple, asyncio.Task] = {}


def file_version(path: Path) -> tuple | None:
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_manifest(path: Path, extract: Callable[[str], str]) -> dict[str, Any]:
    """Reuse a safe parse, with independent data for every reader."""
    path = path.absolute()
    parent = path.parent.stat()
    version = file_version(path)
    key = (str(path), parent.st_dev, parent.st_ino, version, id(extract))
    with _cache_lock:
        data = _cache.get(key)
        if data is None:
            text = path.read_text(encoding='utf-8')
            data = yaml.load(extract(text), Loader=getattr(yaml, 'CSafeLoader', yaml.SafeLoader)) or {}
            if not isinstance(data, dict):
                raise ValueError('video_manifest.md YAML root must be a mapping')
            if file_version(path) == version and len(text) <= 16 * 1024 * 1024:
                _cache[key] = data
                while len(_cache) > 4:
                    _cache.popitem(last=False)
        else:
            _cache.move_to_end(key)
    return deepcopy(data)


async def shared_read(key: tuple, action: Callable[[], Awaitable[Any]]) -> Any:
    """Share only in-flight work; a later request always checks fresh files."""
    scoped = (asyncio.get_running_loop(), key)
    task = _pending.get(scoped)
    if task is None:
        task = asyncio.create_task(action())
        _pending[scoped] = task
        def finished(completed):
            if _pending.get(scoped) is completed:
                _pending.pop(scoped, None)
            if not completed.cancelled():
                completed.exception()  # Observe errors even if all clients disconnect.
        task.add_done_callback(finished)
    return await asyncio.shield(task)
