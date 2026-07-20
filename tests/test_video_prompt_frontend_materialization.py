from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SOURCE = (ROOT / "server" / "web" / "src" / "main.tsx").read_text(encoding="utf-8")


def _callback_source(name: str) -> str:
    marker = f"  const {name} = "
    start = FRONTEND_SOURCE.find(marker)
    assert start >= 0, f"missing frontend callback: {name}"
    next_callback = re.search(r"\n  const [A-Za-z0-9_]+ = ", FRONTEND_SOURCE[start + len(marker) :])
    assert next_callback is not None, f"could not find the end of frontend callback: {name}"
    end = start + len(marker) + next_callback.start()
    return FRONTEND_SOURCE[start:end]


def test_video_prompt_materializer_posts_target_review_items_without_replacing_others() -> None:
    source = _callback_source("materializeVideoPrompts")

    assert "'/api/image-gen/video-prompts/create'" in source
    assert "run_id: runId" in source
    assert "items: buildReviewItems(targetItems)" in source
    assert "replace_all: false" in source
    assert "approve_for_generation: true" in source


def test_single_video_generation_materializes_once_before_provider_call() -> None:
    source = _callback_source("generateVideoForCut")

    materialize_index = source.index("await materializeVideoPrompts([item])")
    generation_index = source.index("await generateVideoRequest(item)")

    assert "await saveCurrentReview()" not in source
    assert materialize_index < generation_index
    assert source.count("await materializeVideoPrompts([item])") == 1
    assert "materializeVideoPrompts" in source[source.rfind("}, [") :]
    assert "ensureVideoItemsInState([item])" in source
    assert "ensureItemsInState([item])" not in source


def test_bulk_video_generation_materializes_target_set_once_before_workers_start() -> None:
    source = _callback_source("generateVideoItems")

    materialize_index = source.index("await materializeVideoPrompts(targetItems)")
    workers_start_index = source.index("await Promise.all")

    assert "await saveCurrentReview()" not in source
    assert materialize_index < workers_start_index
    assert source.count("await materializeVideoPrompts(targetItems)") == 1
    assert "materializeVideoPrompts" in source[source.rfind("}, [") :]
    assert "ensureVideoItemsInState(targetItems)" in source


def test_video_workspace_save_uses_video_targets_not_source_cut_items() -> None:
    source = _callback_source("saveCurrentReview")

    assert "workspaceMode === 'video' ? videoTargetItems : visibleItems" in source
    assert "items: buildReviewItems(reviewItems)" in source


def test_video_target_reload_preserves_candidates_and_only_dirty_draft_fields() -> None:
    assert "function mergeLoadedVideoItemsWithLocalState" in FRONTEND_SOURCE
    assert "videoCandidates: previous.videoCandidates" in FRONTEND_SOURCE
    assert "dirtyFields.has('videoDraftPrompt')" in FRONTEND_SOURCE
    assert "dirtyFields.has('videoReferencePaths')" in FRONTEND_SOURCE
    load_source = _callback_source("loadVideoTargets")
    assert "mergeLoadedVideoItemsWithLocalState(prev, loadedItems)" in load_source


def test_generation_payload_keeps_frontend_prompt_as_authoring_source() -> None:
    source = _callback_source("buildVideoGenerateItem")

    assert "prompt: item.videoDraftPrompt" in source
    assert "item.videoInputMode === 'reference_images' ? ''" in source


def test_reference_image_mode_does_not_recreate_a_first_frame_from_references() -> None:
    assert "videoInputMode?: string" in FRONTEND_SOURCE
    assert "item.videoInputMode === 'reference_images'" in FRONTEND_SOURCE
    materialize_source = _callback_source("buildReviewItems")
    assert "item.videoInputMode === 'reference_images' ? ''" in materialize_source
