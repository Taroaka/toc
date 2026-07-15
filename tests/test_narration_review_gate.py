from __future__ import annotations

from copy import deepcopy

import pytest

from toc.narration_arc import narration_text_set_hash
from toc.narration_revision import ensure_narration_revision
from toc.narration_review_gate import deterministic_narration_review_blockers


def _manifest() -> dict:
    narration = {
        "text": "主人公は波音を聞き、迷いの理由を認めます。",
        "tts_text": "主人公は波音を聞き、迷いの理由を認めます。",
        "tool": "elevenlabs",
        "authoring_status": "human_locked",
        "review": {"agent_review_ok": True, "human_review_ok": False},
    }
    ensure_narration_revision(narration)
    data = {
        "scenes": [
            {
                "scene_id": 0,
                "image_generation": {"output": "assets/characters/hero.png"},
                "audio": {"narration": {"review": {"agent_review_ok": False}}},
            },
            {
                "scene_id": 1,
                "cuts": [
                    {"cut_id": 1, "audio": {"narration": narration}},
                    {
                        "cut_id": 2,
                        "status": "deleted",
                        "audio": {"narration": {"review": {"agent_review_ok": False}}},
                    },
                    {
                        "cut_id": 3,
                        "kind": "location_reference",
                        "audio": {"narration": {"review": {"agent_review_ok": False}}},
                    },
                ],
            },
        ]
    }
    data["narration_workflow"] = {
        "arc_review": {
            "status": "passed",
            "narration_text_set_hash": narration_text_set_hash(data),
            "findings": [],
        }
    }
    return data


def test_shared_deterministic_gate_uses_active_inventory_and_current_global_arc() -> None:
    assert deterministic_narration_review_blockers(_manifest()) == []


@pytest.mark.parametrize("layer", ["semantic", "delivery"])
def test_shared_deterministic_gate_blocks_stale_local_review_layers(layer: str) -> None:
    data = _manifest()
    narration = data["scenes"][1]["cuts"][0]["audio"]["narration"]
    narration["review"][layer] = {"status": "stale"}

    assert deterministic_narration_review_blockers(data) == ["scene1_cut1"]


def test_shared_deterministic_gate_requires_reason_for_revision_human_override() -> None:
    data = _manifest()
    review = data["scenes"][1]["cuts"][0]["audio"]["narration"]["review"]
    review.update({"agent_review_ok": False, "human_review_ok": True})
    assert deterministic_narration_review_blockers(data) == ["scene1_cut1"]

    review["human_review_reason"] = "意図した反復としてproducerが確認"
    assert deterministic_narration_review_blockers(data) == []


def test_shared_deterministic_gate_blocks_local_arc_and_stale_global_hash() -> None:
    data = _manifest()
    review = data["scenes"][1]["cuts"][0]["audio"]["narration"]["review"]
    review["narration_arc_review"] = {"status": "changes_requested"}
    assert deterministic_narration_review_blockers(data) == ["scene1_cut1"]

    changed = deepcopy(_manifest())
    changed["scenes"][1]["cuts"][0]["audio"]["narration"]["text"] += "それでも歩き出します。"
    assert deterministic_narration_review_blockers(changed) == ["full_run_arc"]
