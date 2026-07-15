from __future__ import annotations

from copy import deepcopy

from toc.narration_arc import narration_text_set_hash, validate_audio_story_contract


def _manifest() -> dict:
    return {
        "audio_story_plan": {
            "authoring_status": "authored",
            "authoring_provenance": "audio_story_director",
            "audience_promise": "失われた約束の行方を追う",
            "narrator_bible": {
                "relationship_to_story": "companion",
                "emotional_permission": ["主人公の迷いに寄り添う"],
                "forbidden_attitudes": ["結末を先に断定しない"],
            },
            "continuous_full_draft": "彼は約束を思い出します。\nそして帰る道を選びます。",
            "scene_arcs": [
                {
                    "scene_id": 1,
                    "attention_state": "release",
                    "audience_state_before": "帰る理由を知らない",
                    "audience_state_after": "約束が理由だと理解する",
                    "semantic_load": "medium",
                }
            ],
            "open_loops": [
                {
                    "loop_id": "promise",
                    "opened_at": "scene1_cut1",
                    "payoff_at": "scene1_cut2",
                    "payoff_type": "answer",
                }
            ],
        },
        "narration_spans": [
            {
                "span_id": "ns_001",
                "source_cut_ids": ["scene1_cut1", "scene1_cut2"],
                "story_job": "aftertaste",
                "opened_loop_ids": ["promise"],
                "closed_loop_ids": ["promise"],
                "text": "彼は約束を思い出します。\nそして帰る道を選びます。",
                "tts_text": "かれは やくそくを おもいだします。\nそして かえる みちを えらびます。",
                "audio_visual_relation": "complement",
                "tts_generation_group_id": "scene1_flow",
            }
        ],
        "scenes": [
            {
                "scene_id": 1,
                "cuts": [
                    {
                        "cut_id": 1,
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "authoring_status": "human_locked",
                                "text": "彼は約束を思い出します。",
                                "tts_text": "かれは やくそくを おもいだします。",
                            }
                        },
                    },
                    {
                        "cut_id": 2,
                        "audio": {
                            "narration": {
                                "tool": "elevenlabs",
                                "authoring_status": "human_locked",
                                "text": "そして帰る道を選びます。",
                                "tts_text": "そして かえる みちを えらびます。",
                            }
                        },
                    },
                ],
            }
        ],
    }


def test_full_run_audio_story_contract_accepts_cross_cut_span() -> None:
    assert validate_audio_story_contract(_manifest()) == []


def test_full_run_audio_story_contract_rejects_missing_plan_and_unanchored_voice() -> None:
    data = _manifest()
    data["audio_story_plan"] = {}
    data["narration_spans"] = []

    findings = validate_audio_story_contract(data)

    assert "audio_story_plan.audience_promise is required" in findings
    assert "narration_spans must contain at least one full-run span" in findings
    assert any("scene1_cut1" in finding and "not anchored" in finding for finding in findings)


def test_narration_text_set_hash_changes_with_plan_span_or_cut_text() -> None:
    original = _manifest()
    baseline = narration_text_set_hash(original)
    plan_edit = deepcopy(original)
    plan_edit["audio_story_plan"]["audience_promise"] = "別の約束"
    span_edit = deepcopy(original)
    span_edit["narration_spans"][0]["tts_generation_group_id"] = "other_group"
    cut_edit = deepcopy(original)
    cut_edit["scenes"][0]["cuts"][0]["audio"]["narration"]["text"] = "別の本文"

    assert narration_text_set_hash(plan_edit) != baseline
    assert narration_text_set_hash(span_edit) != baseline
    assert narration_text_set_hash(cut_edit) != baseline


def test_narration_text_set_hash_ignores_deleted_and_reference_only_nodes() -> None:
    data = _manifest()
    baseline = narration_text_set_hash(data)
    data["scenes"].append(
        {
            "scene_id": 9,
            "kind": "location_reference",
            "audio": {"narration": {"text": "参照用で読み上げない文面"}},
        }
    )
    data["scenes"][0]["cuts"].append(
        {
            "cut_id": 99,
            "cut_status": "deleted",
            "audio": {"narration": {"text": "削除済みで読み上げない文面"}},
        }
    )

    assert narration_text_set_hash(data) == baseline


def test_full_run_audio_story_contract_rejects_ambiguous_tts_continuity_group() -> None:
    data = _manifest()
    extra = deepcopy(data["narration_spans"][0])
    extra.update(
        {
            "span_id": "ns_002",
            "source_cut_ids": ["scene1_cut1"],
            "text": "",
            "tts_text": "",
            "audio_visual_relation": "voice_silence",
            "tts_generation_group_id": "other_flow",
        }
    )
    data["narration_spans"].append(extra)
    # A voiced span in another group makes the provider's adjacent context ambiguous.
    extra["audio_visual_relation"] = "complement"
    extra["text"] = "彼は約束を思い出し"
    extra["tts_text"] = "かれは やくそくを おもいだし"

    findings = validate_audio_story_contract(data)

    assert any("scene1_cut1" in finding and "more than one" in finding for finding in findings)


def test_full_run_audio_story_contract_binds_spans_to_actual_cut_script() -> None:
    data = _manifest()
    data["scenes"][0]["cuts"][1]["audio"]["narration"]["text"] = "無関係な結末です。"

    findings = validate_audio_story_contract(data)

    assert any("ns_001" in finding and "source_cut_ids narration" in finding for finding in findings)


def test_full_run_audio_story_contract_preserves_audible_punctuation() -> None:
    data = _manifest()
    data["narration_spans"][0]["text"] = "彼は約束を思い出します！\nそして帰る道を選びます。"

    findings = validate_audio_story_contract(data)

    assert any("ns_001" in finding and "source_cut_ids narration" in finding for finding in findings)


def test_full_run_audio_story_contract_ignores_character_reference_scenes() -> None:
    data = _manifest()
    data["scenes"].insert(
        0,
        {
            "scene_id": 0,
            "scene_kind": "character_reference",
            "image_generation": {"output": "assets/characters/hero.png"},
        },
    )

    assert validate_audio_story_contract(data) == []


def test_derived_legacy_audio_story_requires_full_run_author_review() -> None:
    data = _manifest()
    data["audio_story_plan"]["authoring_status"] = "changes_requested"
    data["audio_story_plan"]["authoring_provenance"] = "derived_legacy_cut_projection"

    assert any("Audio Story Director review" in finding for finding in validate_audio_story_contract(data))

    data["audio_story_plan"]["authoring_status"] = "authored"
    assert any("full-run-first reauthoring" in finding for finding in validate_audio_story_contract(data))


def test_full_run_audio_story_contract_rejects_reverse_cut_and_span_order() -> None:
    data = _manifest()
    span = data["narration_spans"][0]
    span["source_cut_ids"] = ["scene1_cut2", "scene1_cut1"]
    span["text"] = "そして帰る道を選びます。\n彼は約束を思い出します。"
    span["tts_text"] = "そして かえる みちを えらびます。\nかれは やくそくを おもいだします。"
    data["audio_story_plan"]["continuous_full_draft"] = span["text"]

    findings = validate_audio_story_contract(data)

    assert any("canonical cut order" in finding for finding in findings)


def test_full_run_audio_story_contract_validates_open_loop_identity_and_timing() -> None:
    data = _manifest()
    data["narration_spans"][0]["opened_loop_ids"].append("ghost")
    data["audio_story_plan"]["open_loops"].append(
        deepcopy(data["audio_story_plan"]["open_loops"][0])
    )
    data["audio_story_plan"]["open_loops"][0]["opened_at"] = "scene1_cut2"
    data["audio_story_plan"]["open_loops"][0]["payoff_at"] = "scene1_cut1"
    data["audio_story_plan"]["open_loops"][1]["opened_at"] = "scene9_cut9"

    findings = validate_audio_story_contract(data)

    assert any("undeclared open loop: ghost" in finding for finding in findings)
    assert any("duplicate audio_story_plan.open_loops" in finding for finding in findings)
    assert any("opened_at references unknown cut scene9_cut9" in finding for finding in findings)
    assert any("opened_at must precede payoff_at" in finding for finding in findings)
