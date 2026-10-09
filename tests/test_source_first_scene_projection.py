"""The p300/p400 boundary must not turn source facts into a fixed plot."""
from copy import deepcopy
import json

import pytest

from test_toc_immersive_frontend_run import load_frontend_run_module, write_test_llm_story as _write_test_llm_story
from story_profile_fixture import _story_profile, _build_research
from toc.visual_planning_contract import bind_visual_value, source_binding


def write_test_llm_story(**kwargs):
    """Supply explicit cut transitions rather than rely on synthetic filler cuts."""
    from math import ceil
    m = load_frontend_run_module()
    _write_test_llm_story(**kwargs)
    path = kwargs['run_dir'] / 'story.md'
    story = m.load_structured_document(path)[1]
    for scene in story['script']['scenes']:
        beat = scene['event_sequence'][0]
        count = ceil(scene['target_duration_seconds'] / 15)
        beat['cut_transitions'] = [dict(
            transition_id=f"{beat['beat_id']}_t{i}",
            first_frame_brief=f"手元の部品{i}が台の上に置かれている",
            motion_brief=f"手元の部品{i}を持ち上げる",
            motion_end_state=f"手元の部品{i}が手の中にある",
        ) for i in range(count)]
    path.write_text(m._md_yaml('story', story))


def setup_profile(tmp_path):
    m = load_frontend_run_module()
    profile = _story_profile("海辺の修理工", "海辺の修理工")
    research = _build_research("海辺の修理工", "海辺の修理工", "2026-09-19T00:00:00Z", profile)
    (tmp_path / "research.md").write_text(m._md_yaml("research", research))
    write_test_llm_story(run_dir=tmp_path, topic="海辺の修理工", target_duration_seconds=300)
    story = m.load_structured_document(tmp_path / "story.md")[1]
    # A genuine source ambiguity, not a placeholder to fill with pressure or a moral.
    scene = story["script"]["scenes"][0]
    scene["conflict"] = ""
    scene["scene_intent"] = {"story_purpose": scene["purpose"]}
    scene["start_state"]["audience_knowledge"] = ["彼女の理由は分からない"]
    scene["end_state"]["audience_knowledge"] = ["彼女の理由は分からない"]
    (tmp_path / "story.md").write_text(m._md_yaml("story", story))
    raw = {name: (tmp_path / f"{name}.md").read_bytes() for name in ("research", "story")}
    visual = bind_visual_value({"scene_visual_values": [{"scene_selector": s["scene_id"], "notes": []} for s in story["script"]["scenes"]]}, raw)
    (tmp_path / "visual_value.md").write_text(m._md_yaml("visual", visual))
    profile = m._profile_from_research(profile, research)
    profile = m._profile_from_story(profile, story)
    profile["visual_planning"] = visual
    profile["visual_value_binding"] = source_binding("visual_value.md", (tmp_path / "visual_value.md").read_bytes())
    return m, profile, story, visual


def test_source_intent_preserves_knowledge_without_generic_pressure(tmp_path):
    m, profile, story, visual = setup_profile(tmp_path)
    intent = m._scene_intent_for_cut_design(title=profile["scene_titles"][0], idx=1,
        location_spec=m._location_spec_for_scene(profile, 1), profile=profile, include_artifact=False)
    assert intent.get("scene_value_amplification") is None
    assert intent.get("visual_notes") == []
    assert intent["audience_knowledge_delta"]["before_scene"] == ["彼女の理由は分からない"]
    assert intent.get("dramatic_question", "") == ""
    assert intent["start_state"] == story["script"]["scenes"][0]["start_state"]
    assert "緊張から" not in json.dumps(intent, ensure_ascii=False)


def test_source_event_preserves_authored_beats_and_does_not_invent_reaction(tmp_path):
    m, profile, story, _ = setup_profile(tmp_path)
    scene = story["script"]["scenes"][0]
    scene["event_sequence"][0].pop("visible_reaction", None)
    profile["story_scenes"] = story["script"]["scenes"]
    event = m._scene_event_for_cut_design(title=profile["scene_titles"][0], idx=1,
        scene_intent={}, location_name="工房", location_id="workshop", profile=profile, include_artifact=False)
    beat = event["event_sequence"][0]
    assert beat["beat_id"] == scene["event_sequence"][0]["beat_id"]
    assert beat["what_happens"] == scene["event_sequence"][0]["what_happens"]
    assert beat.get("visible_reaction", "") == ""


def test_success_cost_and_sincere_explanation_remain_distinct_downstream(tmp_path):
    m, profile, story, visual = setup_profile(tmp_path)
    scene = story["script"]["scenes"][0]
    beat = scene["event_sequence"][0]
    beat["what_happens"] = "修理は成功する。相手は返事をせず席を離れる。"
    beat["dialogue"] = [{"speaker": "主人公", "text": "あなたのために直した", "source_refs": ["P_statement"]}]
    beat["observation"] = {"text": "相手は返事をせず席を離れた", "source_refs": ["P_action"]}
    scene["preservation"]["interpretation_boundary"] = "本人は誠実。相手の理由は不明。和解も改心も確定しない。"
    scene["end_state"]["audience_knowledge"] = ["修理が成功した", "関係の修復は確認できない"]
    (tmp_path / "story.md").write_text(m._md_yaml("story", story))
    raw = {name: (tmp_path / f"{name}.md").read_bytes() for name in ("research", "story")}
    visual = bind_visual_value(visual, raw)
    (tmp_path / "visual_value.md").write_text(m._md_yaml("visual", visual))
    script, manifest, _ = m._build_script_and_manifest("海辺の修理工", tmp_path, "2026-09-19", profile)
    for output in (script, manifest):
        projected = output["scenes"][0]
        event = projected["scene_event"]["event_sequence"][0]
        assert event["what_happens"] == beat["what_happens"]
        assert event["dialogue"] == beat["dialogue"]
        assert event["observation"] == beat["observation"]
        assert projected["scene_intent"]["preservation"] == scene["preservation"]
        assert projected["scene_intent"]["end_state"] == scene["end_state"]
    context = script["scenes"][0]["scene_generation"]["scene_authoring_context"]
    assert context["source_story_scene"] == scene


def test_source_first_compiles_without_legacy_meaning_and_passes_projection(tmp_path):
    from toc.adaptation_value_contract import script_adaptation_issues, manifest_adaptation_issues, source_value_ids
    m, profile, story, visual = setup_profile(tmp_path)
    script, manifest, selectors = m._build_script_and_manifest("海辺の修理工", tmp_path, "2026-09-19T00:00:00Z", profile)
    assert selectors
    assert script_adaptation_issues(script, source_value_ids=source_value_ids(story), visual_value=visual) == []
    assert manifest_adaptation_issues(manifest, source_value_ids=source_value_ids(story), script=script) == []
    assert [s["source_story_scene_id"] for s in script["scenes"]] == [s["scene_id"] for s in story["script"]["scenes"]]
    for scene in script["scenes"]:
        assert scene["scene_intent"]["visual_notes"] == []
        assert "scene_value_amplification" not in scene["scene_intent"]
        assert all("expressive_contract" not in c["cut_contract"] for c in scene["cuts"])
        for cut in scene["cuts"]:
            contract = cut["cut_contract"]
            assert contract["viewer_contract"]["mixed_affect_design"]["mode"] == "none"
            assert contract["viewer_contract"]["emotional_micro_shift"] == {}
            assert contract.get("cut_character_emotion_transition") == {}
    altered = deepcopy(script)
    altered["scenes"][0]["scene_intent"]["visual_notes"] = ["invented instruction"]
    assert script_adaptation_issues(altered, source_value_ids=source_value_ids(story), visual_value=visual)
    altered = deepcopy(manifest)
    altered["video_metadata"]["source_visual_value"]["sha256"] = "sha256:" + "0" * 64
    assert manifest_adaptation_issues(altered, source_value_ids=source_value_ids(story), script=script)


def test_frontend_invokes_visual_author_and_stops_before_script_on_failure(tmp_path):
    m = load_frontend_run_module()
    profile = _story_profile("海辺の修理工", "海辺の修理工")
    research = _build_research("海辺の修理工", "海辺の修理工", "2026-09-19", profile)
    for record in research["source_inventory"]:
        record["url"] = "https://example.org/" + record["source_id"]
    def research_author(**kwargs):
        (tmp_path / "research.md").write_text(m._md_yaml("research", research))
    calls = []
    def visual_author(*, run_dir):
        calls.append(run_dir)
        assert (run_dir / "story.md").is_file()
        raise RuntimeError("visual author unavailable")
    with pytest.raises(RuntimeError, match="visual author unavailable"):
        m.materialize_run("海辺の修理工", "海辺の修理工", tmp_path, "p650",
            research_author_runner=research_author, story_author_runner=write_test_llm_story,
            visual_value_author_runner=visual_author)
    assert calls == [tmp_path]
    assert not (tmp_path / "script.md").exists()
    assert "slot.p310.status=failed" in (tmp_path / "state.txt").read_text()


@pytest.mark.parametrize("stop_slot", ["p330", "p450"])
def test_frontend_authoring_stop_publishes_only_requested_stage(tmp_path, stop_slot):
    m = load_frontend_run_module()
    profile = _story_profile("海辺の修理工", "海辺の修理工")
    research = _build_research("海辺の修理工", "海辺の修理工", "2026-09-19", profile)
    for record in research["source_inventory"]:
        record["url"] = "https://example.org/" + record["source_id"]
    def research_author(**kwargs):
        (tmp_path / "research.md").write_text(m._md_yaml("research", research))
    def visual_author(*, run_dir):
        story = m.load_structured_document(run_dir / "story.md")[1]
        raw = {name: (run_dir / f"{name}.md").read_bytes() for name in ("research", "story")}
        visual = bind_visual_value({"scene_visual_values": [{"scene_selector": s["scene_id"], "notes": []} for s in story["script"]["scenes"]]}, raw)
        (run_dir / "visual_value.md").write_text(m._md_yaml("visual", visual))
    from test_p400_cinematic_author import write_test_cinematic_direction
    m.materialize_run("海辺の修理工", "海辺の修理工", tmp_path, stop_slot,
        research_author_runner=research_author, story_author_runner=write_test_llm_story,
        visual_value_author_runner=visual_author, cinematic_author_runner=write_test_cinematic_direction)
    from toc.stage_evaluation.research_story import check_visual_value
    assert check_visual_value(tmp_path, forbid_production_artifacts=(stop_slot == "p330"))[0]["passed"]
    assert (tmp_path / "script.md").exists() == (stop_slot == "p450")
    assert not (tmp_path / "asset_plan.md").exists()
    assert f"slot.{stop_slot}.status=done" in (tmp_path / "state.txt").read_text()
    if stop_slot == "p450":
        assert m.load_structured_document(tmp_path / "video_manifest.md")[1]["manifest_phase"] == "skeleton"
    import subprocess
    import sys
    from pathlib import Path
    repo = Path(__file__).resolve().parents[1]
    checked = subprocess.run([sys.executable, str(repo / "scripts/verify-pipeline.py"),
        "--run-dir", str(tmp_path), "--flow", "immersive", "--profile", "fast", "--stage-target", stop_slot],
        cwd=repo, capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout + checked.stderr


def test_rebuild_detects_stored_v2_and_preserves_input_bytes(tmp_path):
    m, profile, story, visual = setup_profile(tmp_path)
    before = {name: (tmp_path / name).read_bytes() for name in ("research.md", "story.md", "visual_value.md")}
    profile.pop("visual_planning")
    profile.pop("visual_value_binding")
    script, manifest, _ = m._build_script_and_manifest("海辺の修理工", tmp_path, "2026-09-19", profile)
    assert script["script_metadata"]["visual_planning_contract"] == "source_first_v2"
    assert all((tmp_path / name).read_bytes() == data for name, data in before.items())
    (tmp_path / "story.md").write_bytes(before["story.md"] + b"\n")
    with pytest.raises(RuntimeError, match="source_stale"):
        m._build_script_and_manifest("海辺の修理工", tmp_path, "2026-09-19", profile)


def test_theme_is_not_a_prop_in_source_first_manifest_or_asset_plan(tmp_path):
    from test_research_author import document
    m = load_frontend_run_module()
    research = document()
    research["story_materials"]["symbols_and_themes"] = [{"kind": "theme", "item": "二人の間の壁"}]
    research["story_materials"]["chronological_events"][0]["event"] = "灯台守が黙って食事を続ける。"
    research["story_materials"]["chronological_events"].append({"event_id": "E2", "event": "灯台守が窓を閉める。", "sources": ["S1"]})
    research["story_materials"]["setting"] = {"places": ["食卓"], "time_or_era": ""}
    (tmp_path / "research.md").write_text(m._md_yaml("research", research))
    write_test_llm_story(run_dir=tmp_path, topic="食事の場面", target_duration_seconds=300)
    story = m.load_structured_document(tmp_path / "story.md")[1]
    first, second = story["script"]["scenes"]
    first.update(conflict="", turn="", turning_event={}, scene_intent={"story_purpose": first["purpose"]})
    first["end_state"] = dict(first["start_state"])
    first["handoff_chain"]["outgoing"]["state_id"] = first["end_state"]["state_id"]
    second["start_state"] = dict(first["end_state"])
    second["handoff_chain"]["incoming"]["state_id"] = first["end_state"]["state_id"]
    (tmp_path / "story.md").write_text(m._md_yaml("story", story))
    raw = {name: (tmp_path / f"{name}.md").read_bytes() for name in ("research", "story")}
    visual = bind_visual_value({"scene_visual_values": [{"scene_selector": s["scene_id"], "notes": []} for s in story["script"]["scenes"]]}, raw)
    (tmp_path / "visual_value.md").write_text(m._md_yaml("visual", visual))
    profile = m._profile_from_research(m._story_profile("食事の場面", "原文"), research)
    profile = m._profile_from_story(profile, story)
    profile["visual_planning"] = visual
    profile["visual_value_binding"] = source_binding("visual_value.md", (tmp_path / "visual_value.md").read_bytes())
    script, manifest, _ = m._build_script_and_manifest("食事の場面", tmp_path, "2026-09-19", profile)
    assert manifest["assets"]["object_bible"] == []
    inventory, plan = m._build_asset_artifacts_from_manifest(profile=profile, manifest=manifest)
    assert inventory["asset_inventory"]["coverage_scope"]["reusable_stills"] == []
    assert all(asset["asset_type"] != "object_reference" for asset in plan["assets"])
    assert plan["visual_planning_context"]["source_visual_value"] == profile["visual_value_binding"]
