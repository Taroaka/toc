"""p300 must preserve source identity without inventing an interpretation."""
import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import yaml

from toc.visual_value_authoring import author_visual_value, build_visual_value_prompt
from toc.visual_planning_contract import (
    VISUAL_PLANNING_CONTRACT,
    bind_visual_value,
    validate_visual_value_document,
    validate_visual_value_files,
)


def inputs(tmp_path):
    story = {"script": {"scenes": [
        {"scene_id": "meal", "purpose": "二人が食事を続ける。", "start_state": {"audience_knowledge": ["理由は不明"]}, "end_state": {"audience_knowledge": ["理由は不明"]}},
        {"scene_id": "ending_7", "purpose": "返事をせず戸を閉める。"},
    ]}}
    research = {"source_passages": [{"passage_id": "P1", "passage": "理由を語らず、同じ器で食事を続ける。"}]}
    raw = {}
    for key, data in (("research", research), ("story", story)):
        raw[key] = ("```yaml\n" + yaml.safe_dump(data, allow_unicode=True, sort_keys=False) + "```\n").encode()
        (tmp_path / f"{key}.md").write_bytes(raw[key])
    draft = {"scene_visual_values": [{"scene_selector": s["scene_id"], "notes": []} for s in story["script"]["scenes"]]}
    return story, research, raw, draft


def test_empty_notes_are_valid_but_all_authored_scenes_are_required(tmp_path):
    story, research, raw, draft = inputs(tmp_path)
    doc = bind_visual_value(draft, raw)
    assert validate_visual_value_document(doc, story, research) == []
    assert validate_visual_value_files(tmp_path, doc) == []
    assert doc["visual_value_metadata"]["visual_planning_contract"] == VISUAL_PLANNING_CONTRACT
    assert doc["scene_visual_values"] == draft["scene_visual_values"]


def test_public_visual_validator_dispatches_v2_with_source(tmp_path):
    from toc.adaptation_value_contract import visual_value_adaptation_issues
    story, research, raw, draft = inputs(tmp_path)
    doc = bind_visual_value(draft, raw)
    assert visual_value_adaptation_issues(doc)
    assert visual_value_adaptation_issues(doc, story=story, research=research) == []
    doc["scene_visual_values"].pop()
    assert visual_value_adaptation_issues(doc, story=story)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "order", "bad_notes", "unknown_version", "legacy_block", "bad_pointer", "stale"])
def test_invalid_planning_fails_closed(tmp_path, mutation):
    story, research, raw, draft = inputs(tmp_path)
    doc = bind_visual_value(draft, raw)
    rows = doc["scene_visual_values"]
    if mutation == "missing": rows.pop()
    if mutation == "extra": rows.append({"scene_selector": "absent", "notes": []})
    if mutation == "duplicate": rows[1] = deepcopy(rows[0])
    if mutation == "order": rows.reverse()
    if mutation == "bad_notes": rows[0]["notes"] = ""
    if mutation == "unknown_version": doc["visual_value_metadata"]["visual_planning_contract"] = "unknown"
    if mutation == "legacy_block": rows[0]["scene_value_amplification"] = {"emotional_contradiction": "hope"}
    if mutation == "bad_pointer": doc["continuity_notes"] = [{"source_refs": [{"source": "story", "pointer": "/script/scenes/99"}], "scene_selectors": ["meal"], "note": "same bowl"}]
    if mutation == "stale": (tmp_path / "story.md").write_text("changed source")
    assert validate_visual_value_files(tmp_path, doc)


def test_reference_resolves_and_unknown_extension_is_preserved(tmp_path):
    story, research, raw, draft = inputs(tmp_path)
    draft["continuity_notes"] = [{"source_refs": [{"source": "research", "pointer": "/source_passages/0"}], "scene_selectors": ["meal"], "note": "同じ器の外観を保つ。"}]
    draft["author_comment"] = "心理は確定しない。"
    doc = bind_visual_value(draft, raw)
    assert validate_visual_value_document(doc, story, research) == []
    assert doc["author_comment"] == draft["author_comment"]


def test_source_binding_cannot_escape_run_or_follow_symlink(tmp_path):
    _, _, raw, draft = inputs(tmp_path)
    doc = bind_visual_value(draft, raw)
    doc["visual_value_metadata"]["source_bindings"]["story"]["path"] = "../story.md"
    assert validate_visual_value_files(tmp_path, doc)
    doc = bind_visual_value(draft, raw)
    (tmp_path / "story.md").unlink()
    (tmp_path / "story.md").symlink_to(tmp_path / "research.md")
    assert validate_visual_value_files(tmp_path, doc)


def test_prompt_retains_exact_source_and_no_title_based_profile(tmp_path):
    _, _, raw, _ = inputs(tmp_path)
    prompt = build_visual_value_prompt(research_text=raw["research"].decode(), story_text=raw["story"].decode(), grounding="stage rules")
    assert json.dumps(raw["research"].decode(), ensure_ascii=False) in prompt
    assert json.dumps(raw["story"].decode(), ensure_ascii=False) in prompt
    assert "stage rules" in prompt


def response(draft):
    return SimpleNamespace(payload={"result_json": json.dumps(draft)}, transcript=(), provenance=SimpleNamespace(as_dict=lambda: {"model": "stub"}))


def test_author_publishes_bound_notes_and_keeps_source_unchanged(tmp_path):
    _, _, raw, draft = inputs(tmp_path)
    for row in draft['scene_visual_values']:
        row['boundary_b_roll'] = {'reason': '直接接続を保つ', 'cuts': []}
    turn = AsyncMock(return_value=response(draft))
    doc = asyncio.run(author_visual_value(run_dir=tmp_path, grounding="rules", client_factory=lambda: None, turn_runner=turn))
    assert (tmp_path / "visual_value.md").is_file()
    assert validate_visual_value_files(tmp_path) == []
    assert doc["scene_visual_values"][0]["notes"] == []
    assert (tmp_path / "story.md").read_bytes() == raw["story"]


@pytest.mark.parametrize("failure", ["transport", "invalid", "stale"])
def test_failed_author_does_not_replace_previous_artifact(tmp_path, failure):
    _, _, raw, draft = inputs(tmp_path)
    for row in draft['scene_visual_values']:
        row['boundary_b_roll'] = {'reason': '直接接続を保つ', 'cuts': []}
    previous = tmp_path / "visual_value.md"
    previous.write_text("previous authored output")
    async def turn(**kwargs):
        if failure == "transport": raise RuntimeError("offline")
        if failure == "invalid": draft["scene_visual_values"] = []
        if failure == "stale": (tmp_path / "story.md").write_bytes(raw["story"] + b"\n")
        return response(draft)
    with pytest.raises(RuntimeError):
        asyncio.run(author_visual_value(run_dir=tmp_path, grounding="rules", client_factory=lambda: None, turn_runner=turn))
    assert previous.read_text() == "previous authored output"


def test_raw_yaml_source_uses_the_same_contract_as_markdown(tmp_path):
    story, research, _, draft = inputs(tmp_path)
    raw = {key: yaml.safe_dump(value, allow_unicode=True).encode() for key, value in (("story", story), ("research", research))}
    for key, value in raw.items():
        (tmp_path / f"{key}.md").write_bytes(value)
    assert validate_visual_value_files(tmp_path, bind_visual_value(draft, raw)) == []


def test_downstream_readset_includes_existing_visual_planning_without_requiring_legacy_file(tmp_path):
    from toc.grounding import resolve_stage_grounding
    (tmp_path / "story.md").write_text("story source")
    before = resolve_stage_grounding(stage="script", run_dir=tmp_path, flow="immersive")
    assert "visual_value.md" not in [entry["path"] for entry in before["resolved_paths"]["inputs"]]
    (tmp_path / "visual_value.md").write_text("visual source")
    after = resolve_stage_grounding(stage="script", run_dir=tmp_path, flow="immersive")
    assert "visual_value.md" in [entry["path"] for entry in after["resolved_paths"]["inputs"]]


def test_author_revises_using_validation_error(tmp_path):
    _, _, _, draft = inputs(tmp_path)
    for row in draft['scene_visual_values']:
        row['boundary_b_roll'] = {'reason': '直接接続', 'cuts': []}
    invalid = deepcopy(draft)
    invalid['scene_visual_values'].pop()
    from toc.production_repair import digest
    corrected = response(draft)
    corrected.payload = {'unit_id': 'visual_value', 'base_digest': digest(invalid), 'operations': [{'path': '/scene_visual_values/1',
        'value': json.dumps(draft['scene_visual_values'][1])}]}
    turn = AsyncMock(side_effect=[response(invalid), corrected])
    asyncio.run(author_visual_value(run_dir=tmp_path, grounding='rules', client_factory=lambda: None, turn_runner=turn))
    assert turn.await_count == 2
    prompt = turn.call_args_list[1].kwargs['prompt']
    assert 'visual_value.scene_coverage_or_order' in prompt
    assert 'base_digest' in prompt
    assert 'operations' in turn.call_args_list[1].kwargs['output_schema']['properties']
    assert validate_visual_value_files(tmp_path) == []
