import asyncio
from pathlib import Path
from unittest.mock import Mock

from server import display_reads as reads


def test_manifest_cache_invalidates_and_returns_independent_data(tmp_path):
    path = tmp_path / 'video_manifest.md'
    path.write_text('items: [one]\n')
    extract = Mock(side_effect=lambda text: text)
    first = reads.read_manifest(path, extract)
    first['items'].append('mutation')
    assert reads.read_manifest(path, extract) == {'items': ['one']}
    assert extract.call_count == 1
    path.write_text('items: [two]\n')
    assert reads.read_manifest(path, extract) == {'items': ['two']}
    assert extract.call_count == 2


def test_shared_read_coalesces_and_is_not_cancelled_by_one_waiter():
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []
        async def work():
            calls.append(1); started.set(); await release.wait(); return {'ok': True}
        first = asyncio.create_task(reads.shared_read(('run', 'items'), work))
        await started.wait()
        second = asyncio.create_task(reads.shared_read(('run', 'items'), work))
        await asyncio.sleep(0)
        first.cancel()
        try: await first
        except asyncio.CancelledError: pass
        release.set()
        assert await second == {'ok': True}
        assert len(calls) == 1
        await reads.shared_read(('run', 'items'), work)
        assert len(calls) == 2
    asyncio.run(scenario())


def test_failed_shared_read_can_retry():
    async def scenario():
        async def bad(): raise ValueError('broken')
        try: await reads.shared_read(('bad',), bad)
        except ValueError: pass
        async def good(): return 42
        assert await reads.shared_read(('bad',), good) == 42
    asyncio.run(scenario())


def test_replaced_manifest_invalidates_even_when_size_and_mtime_match(tmp_path):
    import os
    path = tmp_path / 'video_manifest.md'
    path.write_text('value: one\n')
    extract = lambda text: text
    assert reads.read_manifest(path, extract) == {'value': 'one'}
    previous = path.stat()
    replacement = tmp_path / 'replacement'
    replacement.write_text('value: two\n')
    os.utime(replacement, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    replacement.replace(path)
    assert reads.read_manifest(path, extract) == {'value': 'two'}


def test_display_yaml_loader_does_not_construct_python_objects(tmp_path):
    import pytest
    import yaml
    path = tmp_path / 'video_manifest.md'
    path.write_text('!!python/object:builtins.object {}')
    with pytest.raises(yaml.YAMLError):
        reads.read_manifest(path, lambda text: text)
