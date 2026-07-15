from __future__ import annotations

from toc.narration_continuity import (
    invalidate_stale_tts_context_audio,
    narration_cut_index,
    reconcile_audio_story_text,
    tts_continuity_contexts,
)


def _data() -> dict:
    return {
        "audio_story_plan": {"continuous_full_draft": ""},
        "narration_spans": [
            {
                "span_id": f"ns_{index:03d}",
                "source_cut_ids": [f"scene1_cut{index}"],
                "story_job": "setup" if index < 3 else "aftertaste",
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "story_flow",
                "text": "",
                "tts_text": "",
            }
            for index in range(1, 4)
        ],
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {
                        "cut_id": index,
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "text": public,
                                "tts_text": tts,
                                "candidates": [],
                            }
                        },
                    }
                    for index, public, tts in (
                        (1, "始まりです。", "はじまりです。"),
                        (2, "迷いが生まれます。", "まよいが うまれます。"),
                        (3, "答えを選びます。", "こたえを えらびます。"),
                    )
                ],
            }
        ],
    }


def test_reconcile_audio_story_text_projects_cut_edits_into_spans_and_full_draft() -> None:
    data = _data()

    assert reconcile_audio_story_text(data) is True

    assert data["narration_spans"][1]["text"] == "迷いが生まれます。"
    assert data["audio_story_plan"]["continuous_full_draft"] == (
        "始まりです。\n迷いが生まれます。\n答えを選びます。"
    )


def test_continuity_index_excludes_deleted_and_reference_only_nodes() -> None:
    data = _data()
    data["scenes"].insert(
        0,
        {
            "scene_id": 0,
            "image_generation": {"output": "assets/characters/hero.png"},
        },
    )
    data["scenes"][1]["cuts"][1]["cut_status"] = "deleted"

    order, _cuts, _aliases = narration_cut_index(data)

    assert order == ["scene1_cut1", "scene1_cut3"]


def test_neighbor_edit_invalidates_audio_frozen_with_old_tts_context() -> None:
    data = _data()
    reconcile_audio_story_text(data)
    old_context = tts_continuity_contexts(data)["scene1_cut1"]
    narration = data["scenes"][0]["cuts"][0]["audio"]["narration"]
    narration.update(
        {
            "output": "assets/audio/approved.mp3",
            "status": "audio_ready",
            "generation": {"status": "human_approved", "candidate_id": "candidate-1"},
            "audio_review": {"status": "approved", "approved_candidate_id": "candidate-1"},
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "status": "human_approved",
                    "provider_request": dict(old_context),
                }
            ],
        }
    )

    data["scenes"][0]["cuts"][1]["audio"]["narration"]["tts_text"] = "ためらいが うまれます。"
    reconcile_audio_story_text(data)
    invalidated = invalidate_stale_tts_context_audio(data)

    assert "scene1_cut1" in invalidated
    assert narration["candidates"][0]["status"] == "stale"
    assert narration["output"] == ""
    assert narration["audio_review"]["status"] == "pending"


def test_historical_stale_candidate_does_not_unlock_current_context_audio() -> None:
    data = _data()
    reconcile_audio_story_text(data)
    context = tts_continuity_contexts(data)["scene1_cut1"]
    narration = data["scenes"][0]["cuts"][0]["audio"]["narration"]
    narration.update(
        {
            "output": "assets/audio/current.mp3",
            "status": "audio_ready",
            "generation": {"status": "human_approved", "candidate_id": "current"},
            "audio_review": {"status": "approved", "approved_candidate_id": "current"},
            "candidates": [
                {
                    "candidate_id": "old",
                    "status": "stale",
                    "provider_request": {"tts_continuity_hash": "sha256:old"},
                },
                {
                    "candidate_id": "current",
                    "status": "human_approved",
                    "provider_request": dict(context),
                },
            ],
        }
    )

    assert invalidate_stale_tts_context_audio(data) == []
    assert narration["output"] == "assets/audio/current.mp3"
    assert narration["audio_review"]["status"] == "approved"
