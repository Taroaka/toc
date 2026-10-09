from pathlib import Path

import pytest

from toc import sound_design as sound


def context():
    return {"video_set_hash": "sha256:video", "duration_seconds": 12.0,
            "videos": [{"item_id": "scene1_cut1", "path": "assets/a.mp4",
                        "start_seconds": 0.0, "duration_seconds": 12.0,
                        "context": "木の扉がゆっくり開く"}]}


def test_approval_is_required_before_sound_generation():
    with pytest.raises(ValueError, match="承認"):
        sound.require_current({}, context())
    plan = seeded_plan(context(), actor="frontend")
    assert {cue["kind"] for cue in plan["cues"]} == {"bgm", "se"}
    assert "木の扉" in plan["cues"][1]["prompt"]
    sound.require_current(plan, context())
    with pytest.raises(ValueError, match="承認"):
        sound.require_current(plan, {**context(), "video_set_hash": "changed"})


def test_selection_requires_current_successful_candidate(tmp_path):
    plan = seeded_plan(context(), actor="frontend")
    cue = plan["cues"][0]
    settings = sound.CueSettings.model_validate(cue)
    with pytest.raises(ValueError, match="候補"):
        sound.update_cue(tmp_path, plan, cue["id"], settings.model_copy(update={"selected_candidate_id": "missing", "enabled": True}))
    audio = tmp_path / "assets/sound/candidate.mp3"
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"audio")
    cue["candidates"] = [{"id": "candidate", "status": "completed", "path": "assets/sound/candidate.mp3",
                          "sha256": sound.file_hash(audio), "request_hash": sound.request_hash(cue), "duration_seconds": 12}]
    sound.update_cue(tmp_path, plan, cue["id"], settings.model_copy(update={"selected_candidate_id": "candidate", "enabled": True}))
    plan["status"] = "completed"
    assert len(sound.render_plan(tmp_path, plan, context())["tracks"]) == 1
    audio.write_bytes(b"changed")
    with pytest.raises(ValueError, match="変更"):
        sound.render_plan(tmp_path, plan, context())


def test_prompt_change_invalidates_selection_but_keeps_candidates(tmp_path):
    plan = seeded_plan(context(), actor="frontend")
    cue = plan["cues"][0]
    cue["candidates"] = [{"id": "old", "status": "failed"}]
    cue["selected_candidate_id"] = "old"
    cue["enabled"] = True
    settings = sound.CueSettings.model_validate({**cue, "prompt": "新しい演奏"})
    sound.update_cue(tmp_path, plan, cue["id"], settings)
    assert cue["selected_candidate_id"] is None
    assert not cue["enabled"]
    assert cue["candidates"][0]["id"] == "old"


@pytest.mark.parametrize("changes", [{"start_seconds": -1}, {"volume_db": float("nan")},
                                     {"duration_seconds": 0}, {"generation_duration_seconds": 601}])
def test_invalid_mix_settings_fail_closed(changes):
    cue = seeded_plan(context(), actor="frontend")["cues"][0]
    with pytest.raises(ValueError):
        sound.CueSettings.model_validate({**cue, **changes})


def test_render_requires_completion_even_with_no_tracks(tmp_path):
    plan = seeded_plan(context(), actor="frontend")
    with pytest.raises(ValueError, match="確定"):
        sound.render_plan(tmp_path, plan, context())
    plan["status"] = "completed"
    assert sound.render_plan(tmp_path, plan, context())["tracks"] == []
    assert "native_tracks" not in sound.render_plan(tmp_path, plan, context())


def test_native_audio_is_disabled_for_legacy_and_bound_when_selected(tmp_path):
    legacy = seeded_plan(context(), actor="frontend")
    assert not legacy["native_tracks"][0]["enabled"]
    native_context = context()
    native_context["videos"][0].update(native_audio_mode="natural_sound", sha256="sha256:clip",
        audio_stream={"index": 1, "identity": "sha256:stream"}, candidate_revision="revision-a")
    plan = seeded_plan(native_context, actor="frontend")
    track = plan["native_tracks"][0]
    assert track["enabled"]
    plan["status"] = "completed"
    snapshot = sound.render_plan(tmp_path, plan, native_context)
    assert snapshot["native_tracks"][0]["stream_index"] == 1
    assert snapshot["native_tracks"][0]["candidate_revision"] == "revision-a"
    changed = context()
    changed["videos"][0].update(native_audio_mode="natural_sound", sha256="sha256:new",
        audio_stream={"index": 1, "identity": "sha256:stream"}, candidate_revision="revision-a")
    with pytest.raises(ValueError, match="変更"):
        sound.render_plan(tmp_path, plan, changed)


def test_provider_requests_have_explicit_models_and_no_voice_dependencies():
    plan = seeded_plan(context(), actor="frontend")
    bgm = sound.provider_request(plan["cues"][0])
    se = sound.provider_request(plan["cues"][1])
    assert bgm["payload"]["force_instrumental"] is True
    assert bgm["payload"]["model_id"] == "music_v2_5"
    assert se["payload"]["model_id"] == "eleven_text_to_sound_v2"
    assert "voice_id" not in bgm["payload"]


def test_path_escape_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        sound.safe_path(tmp_path, "../outside.mp3")


def test_category_mix_defaults_and_snapshot_binding(tmp_path):
    plan = seeded_plan(context(), actor="frontend")
    plan['status'] = 'completed'
    initial = sound.render_plan(tmp_path, plan, context())
    assert initial['mix']['narration'] == {'volume_db': 0, 'muted': False}
    plan['mix'] = sound.MixSettings.model_validate({'se': {'volume_db': 24}, 'bgm': {'muted': True}}).model_dump()
    changed = sound.render_plan(tmp_path, plan, context())
    assert changed['mix']['se']['volume_db'] == 24
    assert changed['mix']['bgm']['muted']
    assert changed['sound_hash'] != initial['sound_hash']


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -61, 37])
def test_category_mix_rejects_invalid_gain(value):
    with pytest.raises(ValueError):
        sound.MixSettings.model_validate({'se': {'volume_db': value}})


def seeded_plan(context, actor='test'):
    """Explicit fixture for pre-existing plans; approval itself now creates no cues."""
    plan = sound.approve(context, actor=actor)
    duration = context['duration_seconds']
    for kind, cue_id, selector, length in [('bgm', 'bgm_main', 'full_run', min(60, max(3,duration))), ('se','se_001',context['videos'][0]['item_id'],min(5,duration))]:
        plan['cues'].append({'id':cue_id,'kind':kind,'label':cue_id,'source_selector':selector,
            'prompt':'木の扉がゆっくり開く' if kind=='se' else '静かな楽器曲',
            'generation_duration_seconds':length,'start_seconds':0,'duration_seconds':duration if kind=='bgm' else length,
            'volume_db':-20 if kind=='bgm' else -12,'fade_in_seconds':0,'fade_out_seconds':0,'loop':kind=='bgm',
            'enabled':False,'selected_candidate_id':None,'candidates':[]})
    return plan
