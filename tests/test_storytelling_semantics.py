"""Reading-derived behaviors: maintained states, unresolved meanings, nonhuman stills."""
import importlib.util
import json
from pathlib import Path

from toc.harness import load_structured_document
from toc.story_authoring import build_research_registry, validate_story_document
from test_research_author import document
from test_toc_immersive_frontend_run import write_test_llm_story
from test_narration_arc import _manifest
from toc.narration_arc import validate_audio_story_contract
import yaml


def test_quiet_scene_can_preserve_state_without_a_fabricated_turn(tmp_path):
    research = document()
    research["story_materials"]["chronological_events"][0]["event"] = "二人は理由を話さず食事を続ける。"
    research["story_materials"]["setting"] = {"places": ["食卓"], "time_or_era": ""}
    (tmp_path / "research.md").write_text(yaml.safe_dump(research, allow_unicode=True))
    write_test_llm_story(run_dir=tmp_path, topic="作品名", target_duration_seconds=300)
    story = load_structured_document(tmp_path / "story.md")[1]
    scene = story["script"]["scenes"][0]
    scene["conflict"] = ""
    scene["turn"] = ""
    scene["turning_event"] = {}
    scene["scene_intent"] = {"story_purpose": scene["purpose"]}
    scene["end_state"] = dict(scene["start_state"])
    scene["handoff_chain"]["outgoing"]["state_id"] = scene["end_state"]["state_id"]
    assert validate_story_document(story, build_research_registry(research)) == []
    scene["turning_event"] = {"beat_id": "does-not-exist", "change": "何かが変わる"}
    assert "story.scene_turning_event_invalid" in validate_story_document(story, build_research_registry(research))


def test_intentionally_unresolved_loop_is_not_rewritten_as_a_required_payoff():
    data = _manifest()
    data["audio_story_plan"]["open_loops"][0].update(payoff_type="intentional_unresolved", payoff_at="")
    data["narration_spans"][0]["closed_loop_ids"] = []
    assert validate_audio_story_contract(data) == []
    path = Path(__file__).resolve().parents[1] / "scripts/ai/toc-immersive-narration-multiagent.py"
    spec = importlib.util.spec_from_file_location("storytelling_narration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    prompt = module._prompt_text(data, ["1"])
    assert "intentional_unresolved" in prompt
    assert "未回収の問いを残さない" not in prompt


def test_nonhuman_first_frame_does_not_get_invented_breathing():
    from toc.video_prompt_compiler import compile_video_api_prompt_v1
    payload = compile_video_api_prompt_v1(cut_contract={
        "visual_planning_contract": "source_first_v2",
        "first_frame_contract": {"first_frame_brief": "無人の岩場。人物はいない。"},
        "motion_contract": {"allowed_new_reveal_elements": []},
    }, first_frame="assets/shore.png", tool="kling_3_0", duration_seconds=5)
    text = json.dumps(payload, ensure_ascii=False)
    assert "呼吸" not in text
    assert "重心移動" not in text


def test_missing_motion_and_frames_is_not_silently_invented():
    import pytest
    from toc.video_prompt_compiler import compile_video_api_prompt_v1
    with pytest.raises(ValueError, match="primary_motion_missing"):
        compile_video_api_prompt_v1(cut_contract={"visual_planning_contract": "source_first_v2", "motion_contract": {"allowed_new_reveal_elements": []}}, tool="kling_3_0", duration_seconds=5)


def test_unknown_video_planning_version_does_not_use_legacy_fallback():
    import pytest
    from toc.video_prompt_compiler import compile_video_api_prompt_v1
    for marker in ("future", "", None):
        with pytest.raises(ValueError, match="planning_version_unknown"):
            compile_video_api_prompt_v1(cut_contract={"visual_planning_contract": marker}, tool="kling_3_0", duration_seconds=5)


def test_render_unit_preserves_planning_version_and_rejects_mixed_sources():
    from toc.video_prompt_compiler import compose_video_render_unit_contract
    import pytest
    cut = {"visual_planning_contract": "source_first_v2", "motion_contract": {"allowed_new_reveal_elements": []}}
    unit = compose_video_render_unit_contract([cut, cut], unit_contract={"motion_contract": {"allowed_new_reveal_elements": [], "motion_brief": "動かない"}})
    assert unit["visual_planning_contract"] == "source_first_v2"
    with pytest.raises(ValueError, match="mixed_planning_versions"):
        compose_video_render_unit_contract([cut, {"motion_contract": {"allowed_new_reveal_elements": []}}])
    unknown = {**cut, "visual_planning_contract": "future"}
    with pytest.raises(ValueError, match="planning_version_unknown"):
        compose_video_render_unit_contract([unknown, unknown])
