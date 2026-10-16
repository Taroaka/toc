from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import yaml
from PIL import Image

from test_p400_cinematic_author import sample
from test_toc_immersive_frontend_run import load_frontend_run_module
from toc.asset_state_variants import (
    AssetStateVariantError,
    normalize_state_variant_bindings,
    required_state_variant_plan_entries,
    validate_result_state_references,
)
from toc.p400_authoring import (
    _resolve_state_variant_request_assets,
    validate_direction,
    validate_scene_direction,
)
from toc.p400_projection import project_scene
from toc.p420_assets import ASSET_RESOLUTION_CONTRACT, extend_asset_bibles
from toc.image_request_snapshot import load_request_snapshot


def _state_variant_fixture(tmp_path):
    story, _sources, resources, rows = sample(tmp_path)
    resources["objects"]["box"] = {
        "name": "箱",
        "references": ["assets/objects/box.png"],
    }
    row = rows[0]
    row["state_variants"] = [{
        "entity_type": "object",
        "asset_id": "box",
        "variant_id": "box_open",
        "transition_id": "box_open_transition",
        "source_event_beat_ids": ["open"],
        "from_state": "蓋が閉じている",
        "to_state": "蓋が開き、内側が見える",
        "generation_prompt": "同じ箱の木目、角の金具、寸法を保ち、蓋が開いて内側が見える参照画。",
    }, {
        "entity_type": "character",
        "asset_id": "keeper",
        "variant_id": "keeper_transformed",
        "transition_id": "keeper_change_transition",
        "source_event_beat_ids": ["open"],
        "from_state": "作業着",
        "to_state": "作業着に煤が付いている",
        "generation_prompt": "同じ修理工の顔、体格、衣装を保ち、上着に煤が付いた状態。",
    }]
    cut = row["cuts"][0]
    cut["object_ids"] = ["box"]
    cut["result_frame"] = {
        "state_variant_refs": [{
            "entity_type": "object", "asset_id": "box", "variant_id": "box_open",
            "transition_id": "box_open_transition",
            "consumer_source_event_beat_ids": ["open"],
        }, {
            "entity_type": "character", "asset_id": "keeper", "variant_id": "keeper_transformed",
            "transition_id": "keeper_change_transition",
            "consumer_source_event_beat_ids": ["open"],
        }],
        "brief": "工房の同じ作業台で、箱の蓋が開き、内側が見えている。",
    }
    row["cuts"][1]["object_ids"] = ["box"]
    row["cuts"][1]["state_variant_refs"] = [{
        "entity_type": "object", "asset_id": "box", "variant_id": "box_open",
        "transition_id": "box_open_transition",
        "consumer_source_event_beat_ids": ["wait"],
    }]
    return story, resources, rows, row


def test_p400_projects_state_asset_and_same_cut_result_frame(tmp_path, monkeypatch):
    story, resources, rows, row = _state_variant_fixture(tmp_path)
    source_scene = story["script"]["scenes"][0]
    assert validate_scene_direction(row, source_scene, resources, None) == []

    _script_scene, manifest_scene = project_scene(
        row,
        source_scene=source_scene,
        scene_id=10,
        resources=resources,
        scene_intent={},
        scene_event=source_scene,
        scene_generation={},
        acceptance_draft={},
        acceptance_binding={},
    )
    manifest = {
        "assets": {
            "character_bible": [{"character_id": "keeper", "reference_images": ["assets/characters/keeper.png"]}],
            "object_bible": [{"object_id": "box", "reference_images": ["assets/objects/box.png"]}],
            "location_bible": [{"location_id": "shop", "reference_images": ["assets/locations/shop.png"]}],
        },
        "scenes": [manifest_scene],
    }
    extend_asset_bibles(manifest, {"resources": resources, "scenes": [row]})

    video = manifest_scene["cuts"][0]["video_generation"]
    result_image = video["result_frame"]["image_generation"]
    variant_path = "assets/objects/box__box_open.png"
    character_variant_path = "assets/characters/keeper__keeper_transformed.png"
    assert variant_path in result_image["references"]
    assert character_variant_path in result_image["references"]
    assert "assets/scenes/scene10_cut01.png" in result_image["references"]
    assert result_image["character_variant_ids"] == ["keeper_transformed"]
    assert result_image["object_variant_ids"] == ["box_open"]
    result_prompt = result_image["api_prompt_payload"]["prompt"]
    assert row["cuts"][0]["first_frame_brief"] not in result_prompt
    assert "蓋が開き、内側が見える" in result_prompt
    assert "同じcutの開始画" in result_prompt
    assert video["last_frame"] == video["result_frame"]["output"]
    assert video["last_frame"] != variant_path

    asset_entries = required_state_variant_plan_entries(manifest)
    assert len(asset_entries) == 2
    plan_by_variant = {item["reference_variant_id"]: item for item in asset_entries}
    assert plan_by_variant["box_open"]["generation_plan"]["reference_inputs"] == ["assets/objects/box.png"]
    assert plan_by_variant["box_open"]["generation_plan"]["output"] == variant_path
    assert plan_by_variant["keeper_transformed"]["generation_plan"]["reference_inputs"] == ["assets/characters/keeper.png"]
    assert plan_by_variant["keeper_transformed"]["generation_plan"]["output"] == character_variant_path

    bound_frames = validate_result_state_references(manifest)
    assert bound_frames[0]["output"] == "assets/scenes/scene10_cut01_result.png"
    assert manifest_scene["cuts"][0]["video_generation"]["last_frame"] == bound_frames[0]["output"]

    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate-assets-from-manifest.py"
    spec = importlib.util.spec_from_file_location("generate_assets_result_frame_materialization_test", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _metadata, guides, scenes = module.parse_manifest_yaml_full(yaml.safe_dump(manifest, allow_unicode=True))
    synthetic = module._result_frame_scene_specs(scenes, bound_frames)
    assert len(synthetic) == 1
    result_scene = synthetic[0]
    module.merge_asset_references_into_scene(
        scene=result_scene,
        guides=guides,
        character_refs_mode="scene",
    )
    assert result_scene.image_output == bound_frames[0]["output"]
    assert result_scene.image_object_variant_ids == ["box_open"]
    assert variant_path in result_scene.image_references
    assert character_variant_path in result_scene.image_references
    assert result_scene.video_generation_contract == {}
    assert "assets/scenes/scene10_cut01.png" in result_scene.image_references
    from server import image_gen_app
    for reference in result_scene.image_references:
        image_path = tmp_path / reference
        image_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 9), (90, 80, 70)).save(image_path)
    first_image_item = SimpleNamespace(
        id="scene10_cut01", output="assets/scenes/scene10_cut01.png", references=[], dependency_references=[]
    )
    result_image_item = SimpleNamespace(
        id="scene10_cut01_result_frame",
        output=result_scene.image_output,
        references=result_scene.image_references,
        dependency_references=[],
    )
    groups = image_gen_app._build_generation_groups(
        [first_image_item, result_image_item], run_dir=tmp_path, kind="scene"
    )
    assert [[item.id for item in group] for group in groups] == [
        ["scene10_cut01"],
        ["scene10_cut01_result_frame"],
    ]

    manifest["manifest_phase"] = "production"
    manifest["video_metadata"] = {"topic": "fixture", "experience": "cinematic_story", "aspect_ratio": "16:9"}
    for cut in manifest_scene["cuts"]:
        first_path = tmp_path / cut["image_generation"]["output"]
        first_path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 9), (10, 20, 30)).save(first_path)
    result_path = tmp_path / "assets/scenes/scene10_cut01_result.png"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 9), (40, 50, 60)).save(result_path)
    (tmp_path / "video_manifest.md").write_text(
        "# Video Manifest\n\n```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n",
        encoding="utf-8",
    )
    (tmp_path / "state.txt").write_text("status=P650\n", encoding="utf-8")
    monkeypatch.setattr(module, "check_manifest_single", lambda *_args, **_kwargs: ({"passed": True, "checks": []}, {}))
    monkeypatch.setattr(sys, "argv", [
        str(script_path),
        "--manifest", str(tmp_path / "video_manifest.md"),
        "--base-dir", str(tmp_path),
        "--materialize-request-files-only",
        "--skip-audio",
    ])
    module.main()
    request_text = (tmp_path / "image_generation_requests.md").read_text(encoding="utf-8")
    assert "## scene10_cut01_result_frame" in request_text
    assert variant_path in request_text
    for asset_path in (
        "assets/characters/keeper.png",
        "assets/characters/keeper__keeper_transformed.png",
        "assets/objects/box.png",
        "assets/objects/box__box_open.png",
        "assets/locations/shop.png",
    ):
        target = tmp_path / asset_path
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (16, 9), (5, 6, 7)).save(target)
    from server import image_gen_app
    contract_manifest = {
        "scenes": [{
            "scene_id": 10,
            "cuts": [{
                "cut_id": 1,
                "image_generation": {"output": "assets/scenes/scene10_cut01.png"},
                "video_generation": deepcopy(video),
            }],
        }],
    }
    contract_issues, required_scene_outputs = image_gen_app._manifest_cut_contract(contract_manifest)
    assert contract_issues == []
    assert "assets/scenes/scene10_cut01.png" in required_scene_outputs
    assert "assets/scenes/scene10_cut01_result.png" in required_scene_outputs
    missing_frame_manifest = deepcopy(contract_manifest)
    del missing_frame_manifest["scenes"][0]["cuts"][0]["video_generation"]["result_frame"]
    missing_frame_issues, _ = image_gen_app._manifest_cut_contract(missing_frame_manifest)
    assert any("required result_frame is missing" in issue for issue in missing_frame_issues)
    image_gen_app._prepare_image_prompt_request_revision(tmp_path, provider_ready=True)
    image_snapshot = load_request_snapshot(
        tmp_path / "image_generation_request_snapshot.json",
        run_dir=tmp_path,
        verify_references=True,
    )
    result_item = next(item for item in image_snapshot.items if item.item_id == "scene10_cut01_result_frame")
    first_frame_dependency = next(
        reference for reference in result_item.references
        if reference.path == "assets/scenes/scene10_cut01.png"
    )
    assert first_frame_dependency.deferred
    assert first_frame_dependency.producer_item_id == "scene10_cut1"
    image_gen_app._validate_image_prompt_request_revision(
        tmp_path,
        yaml.safe_load(module.extract_yaml_block((tmp_path / "video_manifest.md").read_text(encoding="utf-8"))),
        require_resolved_references=True,
        require_compiled_v2=True,
    )
    materialized = yaml.safe_load(module.extract_yaml_block((tmp_path / "video_manifest.md").read_text(encoding="utf-8")))
    ordinary_targets = image_gen_app._manifest_scene_targets(materialized)
    auxiliary_targets = image_gen_app._manifest_scene_targets(
        materialized,
        include_auxiliary_image_targets=True,
    )
    assert all(not target["selector"].endswith("_result_frame") for target in ordinary_targets)
    result_target = next(
        target for target in auxiliary_targets
        if target["selector"].endswith("_result_frame")
    )
    assert result_target["auxiliary_image_target"] is True
    assert result_target["image_generation"]["output"] == "assets/scenes/scene10_cut01_result.png"
    first_video = materialized["scenes"][0]["cuts"][0]["video_generation"]
    result_frame_hash = first_video["api_prompt_payload"]["provider_request_binding"]["execution_options"]["reference_content_sha256"]["assets/scenes/scene10_cut01_result.png"]
    assert first_video["api_prompt_payload"]["provider_request_binding"]["last_frame"] == "assets/scenes/scene10_cut01_result.png"
    Image.new("RGB", (16, 9), (70, 80, 90)).save(result_path)
    module.main()
    rematerialized = yaml.safe_load(module.extract_yaml_block((tmp_path / "video_manifest.md").read_text(encoding="utf-8")))
    next_hash = rematerialized["scenes"][0]["cuts"][0]["video_generation"]["api_prompt_payload"]["provider_request_binding"]["execution_options"]["reference_content_sha256"]["assets/scenes/scene10_cut01_result.png"]
    assert next_hash != result_frame_hash


def test_frontend_and_codex_p500_planners_project_the_same_derived_request(tmp_path):
    manifest = {
        "assets": {
            "character_bible": [],
            "object_bible": [{
                "object_id": "box",
                "reference_images": ["assets/objects/box.png"],
                "fixed_prompts": ["木箱"],
                "cinematic": {"role": "箱の同一性", "visual_subject": "木箱"},
                "reference_variants": [{
                    "variant_id": "box_open",
                    "reference_images": ["assets/objects/box__box_open.png"],
                    "generation_references": ["assets/objects/box.png"],
                    "generation_prompt": "同じ木箱の蓋を開いた状態。",
                    "state_transition": {
                        "transition_id": "open_box",
                        "source_event_beat_ids": ["beat_open"],
                        "from_state": "蓋が閉じている",
                        "to_state": "蓋が開いている",
                    },
                }],
            }],
            "location_bible": [],
        },
        "scenes": [{
            "scene_id": "1",
            "scene_event": {"event_sequence": [{"beat_id": "beat_open"}]},
            "cuts": [{
                "cut_id": "1",
                "selector": "scene1_cut01",
                "cut_contract": {"source_event_contract": {"source_event_beat_ids": ["beat_open"]}},
                "image_generation": {"object_ids": ["box"], "object_variant_ids": []},
                "video_generation": {"result_state_reference": {"required": True, "entity_type": "object", "asset_id": "box", "variant_id": "box_open"}},
            }],
        }],
    }
    expected = required_state_variant_plan_entries(manifest)
    profile = {
        "topic_label": "Fixture",
        "protagonist_name": "Actor",
        "artifact_role": "story object",
        "artifact_visual": "wooden box",
        "story_time": "",
    }
    frontend = load_frontend_run_module()
    _inventory, front_plan = frontend._build_asset_artifacts_from_manifest(profile=profile, manifest=manifest)
    front_variant = next(item for item in front_plan["assets"] if item.get("reference_variant_id") == "box_open")
    frontend._write_asset_request_files(tmp_path, front_plan, profile)
    front_requests = (tmp_path / "asset_generation_requests.md").read_text(encoding="utf-8")

    from server import image_gen_app
    (tmp_path / "asset_plan.md").write_text("# Asset Plan\n\n```yaml\nassets: []\n```\n", encoding="utf-8")
    codex_plan = image_gen_app._project_asset_plan_from_manifest(tmp_path, manifest)
    codex_variant = next(item for item in codex_plan if item.get("reference_variant_id") == "box_open")
    (tmp_path / "video_manifest.md").write_text(
        "# Video Manifest\n\n```yaml\n" + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False) + "```\n",
        encoding="utf-8",
    )
    codex_requests = image_gen_app._write_asset_request_files(tmp_path)
    codex_request = next(item for item in codex_requests if item["output"] == "assets/objects/box__box_open.png")

    assert front_variant["generation_plan"]["output"] == expected[0]["generation_plan"]["output"]
    assert codex_variant["generation_plan"]["output"] == expected[0]["generation_plan"]["output"]
    assert front_variant["generation_plan"]["reference_inputs"] == ["assets/objects/box.png"]
    assert codex_variant["generation_plan"]["reference_inputs"] == ["assets/objects/box.png"]
    assert codex_request["references"] == ["assets/objects/box.png"]
    assert "assets/objects/box.png" in front_requests
    assert "assets/objects/box__box_open.png" in front_requests


def test_p420_state_variant_can_reference_a_verified_same_scene_asset_request():
    rows = [{
        "scene_id": "quiet",
        "state_variants": [{"entity_type": "object", "asset_id": "request:box"}],
        "cuts": [{
            "state_variant_refs": [{"entity_type": "object", "asset_id": "request:box"}],
            "result_frame": {
                "state_variant_refs": [{"entity_type": "object", "asset_id": "request:box"}],
            },
        }],
    }]
    records = [{"scene_id": "quiet", "request_id": "box", "asset_id": "source-object-stable"}]
    resolved = _resolve_state_variant_request_assets(rows, records)
    assert resolved[0]["state_variants"][0]["asset_id"] == "source-object-stable"
    assert resolved[0]["cuts"][0]["state_variant_refs"][0]["asset_id"] == "source-object-stable"
    assert resolved[0]["cuts"][0]["result_frame"]["state_variant_refs"][0]["asset_id"] == "source-object-stable"


def test_full_direction_validation_uses_resolved_state_variant_request_ids(tmp_path, monkeypatch):
    story, resources, rows, _first_row = _state_variant_fixture(tmp_path)
    authored_rows = deepcopy(rows)
    authored_rows[0]["state_variants"][0]["asset_id"] = "request:box"
    for cut in authored_rows[0]["cuts"]:
        for binding in cut.get("state_variant_refs", []):
            if binding.get("asset_id") == "box":
                binding["asset_id"] = "request:box"
        result_frame = cut.get("result_frame")
        if isinstance(result_frame, dict):
            for binding in result_frame.get("state_variant_refs", []):
                if binding.get("asset_id") == "box":
                    binding["asset_id"] = "request:box"
    records = [{"scene_id": "quiet", "request_id": "box", "asset_id": "box"}]
    resolved_rows = _resolve_state_variant_request_assets(authored_rows, records)
    monkeypatch.setattr(
        "toc.p400_authoring.resolve_asset_requests",
        lambda *_args, **_kwargs: (
            deepcopy(resolved_rows),
            deepcopy(resources),
            deepcopy(records),
        ),
    )
    doc = {
        "metadata": {
            "contract": "cinematic_direction_v1",
            "asset_resolution_contract": ASSET_RESOLUTION_CONTRACT,
        },
        "base_resources": deepcopy(resources),
        "resources": deepcopy(resources),
        "scenes": authored_rows,
        "asset_resolutions": records,
    }

    errors = validate_direction(doc, story, resources, research={})

    assert any("asset_resolution_changed" in issue for issue in errors)
    assert not any("state_variant_unbound" in issue for issue in errors)


def test_malformed_result_variant_entries_are_not_silently_filtered():
    with pytest.raises(AssetStateVariantError, match="binding_entry_invalid"):
        normalize_state_variant_bindings({"state_variant_refs": [None]}, strict=True)


def test_p400_allows_later_cut_to_reuse_state_variant_from_its_creation_beat(tmp_path):
    story, resources, rows, first_row = _state_variant_fixture(tmp_path)
    later_row = rows[1]
    resources["objects"]["box"] = {"name": "箱", "references": ["assets/objects/box.png"]}
    first_row["state_variants"][0]["asset_id"] = "box"
    later_cut = later_row["cuts"][0]
    later_cut["object_ids"] = ["box"]
    later_cut["state_variant_refs"] = [{
        "entity_type": "object",
        "asset_id": "box",
        "variant_id": "box_open",
        "transition_id": "box_open_transition",
        "consumer_source_event_beat_ids": ["exit"],
    }]
    later_cut["continuity"]["previous_end_state"] = rows[0]["cuts"][-1]["motion_end_state"]
    known = {("object", "box", "box_open"): first_row["state_variants"][0]}
    errors = validate_scene_direction(
        later_row,
        story["script"]["scenes"][1],
        resources,
        rows[0],
        known_state_variants=known,
    )
    assert errors == []
    _script, later_manifest_scene = project_scene(
        later_row,
        source_scene=story["script"]["scenes"][1],
        scene_id=20,
        resources=resources,
        scene_intent={},
        scene_event=story["script"]["scenes"][1],
        scene_generation={},
        acceptance_draft={},
        acceptance_binding={},
        available_state_variants=[first_row["state_variants"][0]],
    )
    later_image = later_manifest_scene["cuts"][0]["image_generation"]
    assert later_image["object_variant_ids"] == ["box_open"]
    assert "assets/objects/box__box_open.png" in later_image["references"]
    from toc.p400_authoring import bind_direction, validate_direction
    sources = {name: (tmp_path / f"{name}.md").read_bytes() for name in ("research", "story", "visual_value")}
    direction = bind_direction(rows, sources, resources)
    assert not any("state_variant_unbound" in issue for issue in validate_direction(
        direction, story, resources, research={}))


@pytest.mark.parametrize('variant_index', [0, 1])
def test_p400_author_preflight_reuses_prior_scene_result_variant(tmp_path, variant_index):
    import asyncio
    import json
    from toc.p400_authoring import author_cinematic_direction
    from toc.downstream_repair import projection_diagnostics
    from toc.production_diagnostics import AuthoringValidationError

    story, resources, rows, first = _state_variant_fixture(tmp_path)
    later = rows[1]['cuts'][0]
    later['object_ids'] = ['box']
    ref = deepcopy(first['cuts'][0]['result_frame']['state_variant_refs'][variant_index])
    ref['consumer_source_event_beat_ids'] = ['exit']
    later['result_frame'] = {'state_variant_refs': [ref],
        'brief': '工房の作業台の横で、修理工が開いた箱を残している。'}
    before = deepcopy(rows)
    calls = []

    async def turn(**kwargs):
        row = rows[len(calls)]
        calls.append(kwargs)
        return SimpleNamespace(payload={'result_json': json.dumps(row)}, transcript=(),
            provenance=SimpleNamespace(as_dict=lambda: {}))

    result = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources,
        grounding='', client_factory=lambda: None, turn_runner=turn))
    assert len(calls) == 2
    assert result['scenes'] == before
    assert not projection_diagnostics(rows[1], story['script']['scenes'][1], resources,
        available_state_variants=first['state_variants'])
    # Missing provenance remains a failure; the preflight must not silently
    # invent or import variants from a future or otherwise unavailable scene.
    with pytest.raises(AuthoringValidationError, match='variant_unbound'):
        projection_diagnostics(rows[1], story['script']['scenes'][1], resources)

    async def no_generation(**kwargs):
        raise AssertionError('completed scene was regenerated')

    resumed = asyncio.run(author_cinematic_direction(run_dir=tmp_path, resources=resources,
        grounding='', client_factory=lambda: None, turn_runner=no_generation))
    assert resumed['scenes'] == before
    ledger = tmp_path / 'logs/repair/ledger.json'
    assert not ledger.exists() or not json.loads(ledger.read_text())['events']


def test_p400_rejects_later_variant_reference_without_direction_or_resource_definition(tmp_path):
    from toc.p400_authoring import bind_direction, validate_direction

    story, sources, resources, rows = sample(tmp_path)
    resources["objects"]["box"] = {"name": "箱", "references": ["assets/objects/box.png"]}
    rows[1]["cuts"][0]["object_ids"] = ["box"]
    rows[1]["cuts"][0]["state_variant_refs"] = [{
        "entity_type": "object",
        "asset_id": "box",
        "variant_id": "box_open",
        "transition_id": "box_open_transition",
        "consumer_source_event_beat_ids": ["exit"],
    }]
    direction = bind_direction(rows, sources, resources)

    assert rows[0].get("state_variants", []) == []
    assert resources["objects"]["box"].get("reference_variants", []) == []
    errors = validate_direction(direction, story, resources, research={})
    assert any("state_variant_unbound" in issue for issue in errors)


def test_state_variant_asset_is_reused_by_a_later_cut_with_a_different_event_beat():
    manifest = {
        "assets": {"object_bible": [{
            "object_id": "vehicle",
            "reference_images": ["assets/objects/vehicle.png"],
            "reference_variants": [{
                "variant_id": "vehicle_transformed",
                "reference_images": ["assets/objects/vehicle__vehicle_transformed.png"],
                "generation_prompt": "Preserve the parent vehicle identity and draw its source-grounded changed form.",
                "state_transition": {
                    "transition_id": "vehicle_change",
                    "source_event_beat_ids": ["beat_transform"],
                    "from_state": "old form",
                    "to_state": "changed form",
                },
            }],
        }]},
        "scenes": [
            {
                "scene_id": "1",
                "scene_event": {"event_sequence": [{"beat_id": "beat_transform"}]},
                "cuts": [{
                    "cut_id": "1", "selector": "scene1_cut01",
                    "cut_contract": {"source_event_contract": {"source_event_beat_ids": ["beat_transform"]}},
                    "image_generation": {"object_ids": ["vehicle"], "object_variant_ids": []},
                }],
            },
            {
                "scene_id": "2",
                "scene_event": {"event_sequence": [{"beat_id": "beat_after"}]},
                "cuts": [{
                    "cut_id": "1", "selector": "scene2_cut01",
                    "cut_contract": {"source_event_contract": {"source_event_beat_ids": ["beat_after"]}},
                    "image_generation": {"object_ids": ["vehicle"], "object_variant_ids": ["vehicle_transformed"]},
                }],
            },
        ],
    }
    plan = required_state_variant_plan_entries(manifest)
    assert len(plan) == 1
    assert plan[0]["source_script_selectors"] == ["scene2_cut01"]
    wrong_parent = deepcopy(manifest)
    wrong_parent["assets"]["object_bible"].append({
        "object_id": "unrelated",
        "reference_images": ["assets/objects/unrelated.png"],
        "reference_variants": [{
            "variant_id": "vehicle_transformed",
            "reference_images": ["assets/objects/unrelated__vehicle_transformed.png"],
            "generation_prompt": "Unrelated state reference.",
            "state_transition": {
                "transition_id": "unrelated_change",
                "source_event_beat_ids": ["beat_transform"],
                "from_state": "before",
                "to_state": "after",
            },
        }],
    })
    with pytest.raises(AssetStateVariantError, match="unrelated/vehicle_transformed is not selected"):
        required_state_variant_plan_entries(wrong_parent)


def test_required_result_frame_fails_closed_when_missing_or_unsupported():
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as temp_dir:
        _required_result_frame_failure_fixture(Path(temp_dir))


def _required_result_frame_failure_fixture(tmp_path):
    _story, resources, rows, row = _state_variant_fixture(tmp_path)
    _script, manifest_scene = project_scene(
        row,
        source_scene=_story["script"]["scenes"][0],
        scene_id=10,
        resources=resources,
        scene_intent={},
        scene_event=_story["script"]["scenes"][0],
        scene_generation={},
        acceptance_draft={},
        acceptance_binding={},
    )
    manifest = {
        "assets": {
            "character_bible": [{"character_id": "keeper", "reference_images": ["assets/characters/keeper.png"]}],
            "object_bible": [{"object_id": "box", "reference_images": ["assets/objects/box.png"]}],
            "location_bible": [{"location_id": "shop", "reference_images": ["assets/locations/shop.png"]}],
        },
        "scenes": [manifest_scene],
    }
    extend_asset_bibles(manifest, {"resources": resources, "scenes": [row]})
    video = manifest_scene["cuts"][0]["video_generation"]
    del video["result_frame"]
    with pytest.raises(AssetStateVariantError, match="missing its scene-specific result_frame"):
        validate_result_state_references(manifest)

    manifest_scene["cuts"][0]["video_generation"]["result_frame"] = deepcopy(
        project_scene(
            row,
            source_scene=_story["script"]["scenes"][0],
            scene_id=10,
            resources=resources,
            scene_intent={},
            scene_event=_story["script"]["scenes"][0],
            scene_generation={},
            acceptance_draft={},
            acceptance_binding={},
        )[1]["cuts"][0]["video_generation"]["result_frame"]
    )
    manifest_scene["cuts"][0]["video_generation"]["tool"] = "unreviewed_video_provider"
    with pytest.raises(AssetStateVariantError, match="conditioning is unsupported"):
        validate_result_state_references(manifest)


def test_video_reference_content_digest_tracks_result_frame_bytes(tmp_path):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "generate-assets-from-manifest.py"
    spec = importlib.util.spec_from_file_location("generate_assets_state_frame_test", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    result_path = tmp_path / "assets/scenes/scene1_cut01_result.png"
    result_path.parent.mkdir(parents=True)
    result_path.write_bytes(b"result-frame-v1")
    first = module._video_reference_content_sha256s(
        base_dir=tmp_path,
        bindings=["assets/scenes/scene1_cut01_result.png"],
        selector="scene1_cut01",
    )
    result_path.write_bytes(b"result-frame-v2")
    second = module._video_reference_content_sha256s(
        base_dir=tmp_path,
        bindings=["assets/scenes/scene1_cut01_result.png"],
        selector="scene1_cut01",
    )
    assert first["assets/scenes/scene1_cut01_result.png"] == hashlib.sha256(b"result-frame-v1").hexdigest()
    assert second["assets/scenes/scene1_cut01_result.png"] == hashlib.sha256(b"result-frame-v2").hexdigest()
    assert first != second
