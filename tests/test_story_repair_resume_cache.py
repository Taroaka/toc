from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from test_story_author_pipeline import FakeTurnRunner, _research
from toc.production_repair import RepairSession
from toc.story_author_pipeline import (
    StoryAuthorCacheMiss,
    author_story_from_research,
)
from toc.story_field_repair import scene_digest


def _valid_patch(kwargs: dict[str, Any], *, value: str = "C01") -> dict[str, Any]:
    return {
        "scene_id": kwargs["scene_id"],
        "base_digest": scene_digest(kwargs["scene"]),
        "operations": [
            {"path": "/source_basis/character_ids/0", "value": value},
        ],
    }


class _CacheAwareFieldRunner:
    """Author fixture with a cache probe distinct from provider generation."""

    supports_cache_lookup = True

    def __init__(self, *, cache_mode: str, run_dir: Path | None = None) -> None:
        self.base = FakeTurnRunner()
        self.cache_mode = cache_mode
        self.run_dir = run_dir
        self.calls: list[dict[str, Any]] = []
        self.provider_calls: list[dict[str, Any]] = []
        self.stage_event_counts_at_provider: list[int] = []

    async def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        role = kwargs["role"]
        if role == "scene_author":
            result = await self.base(**kwargs)
            # Keep the authored prose and all other fields intact while making
            # one deterministic mechanical reference error for p220 repair.
            if result["scenes"][0]["scene_id"] == "scene_01":
                result["scenes"][0]["source_basis"]["character_ids"] = ["UNKNOWN"]
            return result

        if role == "field_repair":
            if kwargs.get("cache_only"):
                if self.cache_mode == "miss":
                    raise StoryAuthorCacheMiss("field patch cache miss")
                if self.cache_mode == "stale":
                    cached = _valid_patch(kwargs)
                    cached["base_digest"] = "stale-base-digest"
                    return cached
                return _valid_patch(kwargs)
            self.provider_calls.append(kwargs)
            if self.run_dir is not None:
                self.stage_event_counts_at_provider.append(
                    len(_stage_events(self.run_dir))
                )
            return _valid_patch(kwargs)

        return await self.base(**kwargs)


def _run_story(tmp_path: Path, runner: _CacheAwareFieldRunner):
    return asyncio.run(
        author_story_from_research(
            _research(),
            topic="時計",
            target_duration_seconds=300,
            turn_runner=runner,
            max_repair_rounds=1,
            output_path=tmp_path / "story.md",
        )
    )


def _stage_events(tmp_path: Path) -> list[dict[str, Any]]:
    ledger = json.loads((tmp_path / "logs/repair/ledger.json").read_text())
    return [event for event in ledger["events"] if event["stage"] == "p220"]


def _exhaust_stage_budget(tmp_path: Path) -> None:
    RepairSession(tmp_path, "p220", stage_limit=1).feedback(
        "otherunit", {"candidate": "already repaired"}, ["budget already used"]
    )


def test_cached_field_patch_replays_without_feedback_or_provider_when_budget_is_exhausted(
    tmp_path: Path,
) -> None:
    _exhaust_stage_budget(tmp_path)
    runner = _CacheAwareFieldRunner(cache_mode="hit", run_dir=tmp_path)

    result = _run_story(tmp_path, runner)

    assert result.story["script"]["scenes"][0]["source_basis"]["character_ids"] == ["C01"]
    field_calls = [call for call in runner.calls if call["role"] == "field_repair"]
    assert len(field_calls) == 1
    assert field_calls[0]["cache_only"] is True
    assert runner.provider_calls == []
    # The pre-existing reservation is the complete p220 budget; the cache hit
    # cannot append another repair event or invoke RepairSession.feedback.
    assert len(_stage_events(tmp_path)) == 1


def test_cache_miss_reserves_once_before_external_field_generation(tmp_path: Path) -> None:
    runner = _CacheAwareFieldRunner(cache_mode="miss", run_dir=tmp_path)

    result = _run_story(tmp_path, runner)

    assert result.story["script"]["scenes"][0]["source_basis"]["character_ids"] == ["C01"]
    field_calls = [call for call in runner.calls if call["role"] == "field_repair"]
    assert [call.get("cache_only", False) for call in field_calls] == [True, False]
    assert len(runner.provider_calls) == 1
    assert runner.provider_calls[0].get("bypass_cache") is True
    assert runner.stage_event_counts_at_provider == [1]
    # One cache miss is followed by one reserved repair turn, never two
    # budget reservations for the same field unit.
    assert len(_stage_events(tmp_path)) == 1
    assert _stage_events(tmp_path)[0]["target"] == "fields-scene_01"


def test_stale_cached_field_patch_is_rejected_and_provider_bypasses_cache(
    tmp_path: Path,
) -> None:
    runner = _CacheAwareFieldRunner(cache_mode="stale", run_dir=tmp_path)

    result = _run_story(tmp_path, runner)

    assert result.story["script"]["scenes"][0]["source_basis"]["character_ids"] == ["C01"]
    field_calls = [call for call in runner.calls if call["role"] == "field_repair"]
    assert [call.get("cache_only", False) for call in field_calls] == [True, False]
    assert len(runner.provider_calls) == 1
    assert runner.provider_calls[0].get("bypass_cache") is True
    assert runner.stage_event_counts_at_provider == [1]
    assert len(_stage_events(tmp_path)) == 1
