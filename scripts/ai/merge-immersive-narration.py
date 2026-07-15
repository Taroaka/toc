#!/usr/bin/env python3
from __future__ import annotations

import argparse
from copy import deepcopy
import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.immersive_manifest import (
    dotted_id_slug,
    dotted_id_sort_key,
    is_non_renderable_manifest_node,
    make_scene_cut_selector,
    normalize_dotted_id,
    selector_aliases,
    story_scene_ids,
)
from toc.runtime_locks import sync_file_lock
from toc.script_narration import materialize_elevenlabs_tts_text, normalize_stability_profile, normalize_voice_tags


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return m.group(1)


def replace_yaml_block(text: str, new_yaml: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    start, end = m.span(1)
    return text[:start] + new_yaml.rstrip("\n") + text[end:]


def append_state_block(state_path: Path, kv: dict[str, str]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in kv.items()]
    block = "\n".join(lines) + "\n---\n"
    if state_path.exists():
        state_path.write_text(state_path.read_text(encoding="utf-8") + block, encoding="utf-8")
        return
    state_path.write_text(block, encoding="utf-8")


def _normalized_id(value: Any) -> str | None:
    return normalize_dotted_id(value)


def _manifest_id_value(value: Any) -> int | str:
    normalized = _normalized_id(value)
    if normalized is None:
        raise ValueError(f"invalid dotted numeric id: {value!r}")
    return int(normalized) if normalized.isdigit() else normalized


def _audio_path_id(value: Any) -> str:
    normalized = _normalized_id(value)
    if normalized is None:
        raise ValueError(f"invalid dotted numeric id: {value!r}")
    return f"{int(normalized):02d}" if normalized.isdigit() else dotted_id_slug(normalized)


def _as_str(value: Any) -> str:
    return "" if value is None else str(value)


def _load_scratch_file(path: Path) -> tuple[str, dict[str, dict[str, Any]]] | None:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    sid = _normalized_id(data.get("scene_id"))
    if sid is None:
        return None
    raw_cuts = data.get("cuts")
    if not isinstance(raw_cuts, list) or not raw_cuts:
        return None
    out: dict[str, dict[str, Any]] = {}
    for c in raw_cuts:
        if not isinstance(c, dict):
            continue
        cid = _normalized_id(c.get("cut_id"))
        if cid is None:
            continue
        out[cid] = {
            "text": _as_str(c.get("narration_text")).strip(),
            "tts_text": _as_str(c.get("tts_text")).strip()
            or materialize_elevenlabs_tts_text(
                spoken_context=_as_str(c.get("spoken_context")).strip(),
                voice_tags=normalize_voice_tags(c.get("voice_tags")),
                spoken_body=_as_str(c.get("spoken_body")).strip(),
            ),
            "prompt": {
                "spoken_context": _as_str(c.get("spoken_context")).strip(),
                "voice_tags": normalize_voice_tags(c.get("voice_tags")),
                "spoken_body": _as_str(c.get("spoken_body")).strip(),
                "stability_profile": normalize_stability_profile(c.get("stability_profile")),
            },
            "contract": {
                "target_function": _as_str(c.get("target_function")).strip(),
                "must_cover": [str(v).strip() for v in list(c.get("must_cover") or []) if str(v).strip()],
                "must_avoid": [str(v).strip() for v in list(c.get("must_avoid") or []) if str(v).strip()],
                "done_when": [str(v).strip() for v in list(c.get("done_when") or []) if str(v).strip()],
            },
        }
    if not out:
        return sid, {}
    return sid, out


def _load_audio_story_scratch(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    if not path.is_file():
        return None
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Full-run audio story scratch must be a mapping: {path}")
    if str(data.get("schema_version") or "").strip() != "narration_audio_story_scratch_v1":
        raise SystemExit("audio_story.yaml schema_version must be narration_audio_story_scratch_v1")
    plan = data.get("audio_story_plan")
    spans = data.get("narration_spans")
    if not isinstance(plan, dict):
        raise SystemExit("audio_story.yaml audio_story_plan must be a mapping")
    if not isinstance(spans, list):
        raise SystemExit("audio_story.yaml narration_spans must be a list")
    narrator_bible = plan.get("narrator_bible") if isinstance(plan.get("narrator_bible"), dict) else {}
    missing: list[str] = []
    if _as_str(plan.get("schema_version")).strip() != "audio_story_plan_v1":
        missing.append("audio_story_plan.schema_version(audio_story_plan_v1)")
    if _as_str(plan.get("authoring_provenance")).strip() != "audio_story_director":
        missing.append("audio_story_plan.authoring_provenance(audio_story_director)")
    authoring_status = _as_str(plan.get("authoring_status")).strip()
    if authoring_status not in {"authored", "approved"}:
        missing.append("audio_story_plan.authoring_status(authored|approved)")
    if not _as_str(plan.get("audience_promise")).strip():
        missing.append("audio_story_plan.audience_promise")
    if not _as_str(narrator_bible.get("relationship_to_story")).strip():
        missing.append("audio_story_plan.narrator_bible.relationship_to_story")
    if (
        not isinstance(narrator_bible.get("emotional_permission"), list)
        or not narrator_bible.get("emotional_permission")
    ):
        missing.append("audio_story_plan.narrator_bible.emotional_permission")
    if (
        not isinstance(narrator_bible.get("forbidden_attitudes"), list)
        or not narrator_bible.get("forbidden_attitudes")
    ):
        missing.append("audio_story_plan.narrator_bible.forbidden_attitudes")
    if not _as_str(plan.get("continuous_full_draft")).strip():
        missing.append("audio_story_plan.continuous_full_draft")
    if not isinstance(plan.get("scene_arcs"), list) or not plan.get("scene_arcs"):
        missing.append("audio_story_plan.scene_arcs")
    if not spans:
        missing.append("narration_spans")
    elif any(not isinstance(span, dict) for span in spans):
        missing.append("narration_spans[] mappings")
    if missing:
        raise SystemExit("audio_story.yaml is incomplete: " + ", ".join(missing))
    return deepcopy(plan), [deepcopy(span) for span in spans if isinstance(span, dict)]


def _ensure_audio_narration(cut_or_scene: dict, *, scene_id: str, cut_id: str | None) -> dict:
    audio = cut_or_scene.get("audio")
    if not isinstance(audio, dict):
        audio = {}
        cut_or_scene["audio"] = audio
    narration = audio.get("narration")
    if not isinstance(narration, dict):
        narration = {}
        audio["narration"] = narration
    if "tool" not in narration or not str(narration.get("tool") or "").strip():
        narration["tool"] = "elevenlabs"
    if "output" not in narration or not str(narration.get("output") or "").strip():
        if cut_id is None:
            narration["output"] = f"assets/audio/scene{_audio_path_id(scene_id)}_narration.mp3"
        else:
            narration["output"] = (
                f"assets/audio/scene{_audio_path_id(scene_id)}_cut{_audio_path_id(cut_id)}_narration.mp3"
            )
    if "normalize_to_scene_duration" not in narration:
        narration["normalize_to_scene_duration"] = False
    if "text" not in narration:
        narration["text"] = ""
    if "tts_text" not in narration:
        narration["tts_text"] = ""
    return narration


def _normalize_contract(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw or {}
    return {
        "target_function": _as_str(raw.get("target_function")).strip(),
        "must_cover": [str(v).strip() for v in list(raw.get("must_cover") or []) if str(v).strip()],
        "must_avoid": [str(v).strip() for v in list(raw.get("must_avoid") or []) if str(v).strip()],
        "done_when": [str(v).strip() for v in list(raw.get("done_when") or []) if str(v).strip()],
    }


def _script_narration_inventory(script: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cuts: list[dict[str, Any]] = []
    scenes: list[dict[str, Any]] = []
    for scene in list(script.get("scenes") or []):
        if not isinstance(scene, dict) or is_non_renderable_manifest_node(scene):
            continue
        scene_id = _normalized_id(scene.get("scene_id"))
        if scene_id is None:
            continue
        scene_cuts: list[dict[str, Any]] = []
        for cut in list(scene.get("cuts") or []):
            if not isinstance(cut, dict) or is_non_renderable_manifest_node(cut):
                continue
            cut_id = _normalized_id(cut.get("cut_id"))
            if cut_id is None:
                continue
            authoring = cut.get("narration_authoring") if isinstance(cut.get("narration_authoring"), dict) else {}
            tool = _as_str(cut.get("narration_tool") or authoring.get("tool") or "elevenlabs").strip().lower()
            entry = {
                "selector": make_scene_cut_selector(scene_id, cut_id),
                "scene_id": scene_id,
                "cut_id": cut_id,
                "text": _as_str(cut.get("narration")).strip(),
                "tts_text": _as_str(cut.get("tts_text")).strip(),
                "tool": tool,
                "authoring_status": _as_str(authoring.get("status")).strip().lower(),
                "contract": _normalize_contract(
                    cut.get("narration_contract") if isinstance(cut.get("narration_contract"), dict) else {}
                ),
            }
            cuts.append(entry)
            scene_cuts.append(entry)
        scenes.append(
            {
                "scene_id": scene_id,
                "summary": _as_str(scene.get("scene_summary") or scene.get("story_visual")).strip(),
                "cuts": scene_cuts,
            }
        )
    return cuts, scenes


def _validate_canonical_audio_story(
    *,
    plan: dict[str, Any],
    spans: list[dict[str, Any]],
    cut_inventory: list[dict[str, Any]],
) -> list[str]:
    findings: list[str] = []
    alias_to_cut: dict[str, dict[str, Any]] = {}
    voiced_selectors: set[str] = set()
    for cut in cut_inventory:
        for alias in selector_aliases(cut["scene_id"], cut["cut_id"]):
            alias_to_cut[alias] = cut
        if cut["tool"] != "silent" and (cut["text"] or cut["tts_text"]):
            voiced_selectors.add(str(cut["selector"]))

    voiced_ref_counts = {selector: 0 for selector in voiced_selectors}
    voiced_span_texts: list[str] = []
    voiced_source_sequence: list[str] = []
    for index, span in enumerate(spans, start=1):
        label = _as_str(span.get("span_id")).strip() or f"index_{index}"
        if _as_str(span.get("audio_visual_relation")).strip() == "voice_silence":
            continue
        raw_source_ids = span.get("source_cut_ids")
        if not isinstance(raw_source_ids, list):
            findings.append(f"{label}: source_cut_ids must be a list")
            raw_source_ids = []
        source_ids = [_as_str(value).strip() for value in raw_source_ids]
        source_cuts: list[dict[str, Any]] = []
        for selector in source_ids:
            source_cut = alias_to_cut.get(selector)
            if source_cut is None:
                findings.append(f"{label}: unknown source cut {selector or '<empty>'}")
                continue
            source_cuts.append(source_cut)
            canonical = str(source_cut["selector"])
            if canonical in voiced_ref_counts:
                voiced_ref_counts[canonical] += 1
                voiced_source_sequence.append(canonical)
            else:
                findings.append(f"{label}: voiced span cannot source silent cut {canonical}")
        expected_text = "\n".join(str(cut["text"]) for cut in source_cuts if str(cut["text"]).strip())
        expected_tts_text = "\n".join(
            str(cut["tts_text"] or cut["text"])
            for cut in source_cuts
            if str(cut["tts_text"] or cut["text"]).strip()
        )
        actual_text = _as_str(span.get("text")).strip()
        actual_tts_text = _as_str(span.get("tts_text")).strip()
        if actual_text != expected_text:
            findings.append(f"{label}: text must equal newline-joined source cut narration")
        if actual_tts_text != expected_tts_text:
            findings.append(f"{label}: tts_text must equal newline-joined source cut tts_text")
        if not _as_str(span.get("tts_generation_group_id")).strip():
            findings.append(f"{label}: tts_generation_group_id is required")
        if actual_text:
            voiced_span_texts.append(actual_text)
    for selector, count in voiced_ref_counts.items():
        if count != 1:
            findings.append(f"{selector}: voiced cut must be anchored by exactly one voiced narration span (found {count})")
    expected_voiced_sequence = [
        str(cut["selector"])
        for cut in cut_inventory
        if str(cut["selector"]) in voiced_selectors
    ]
    if voiced_source_sequence != expected_voiced_sequence:
        findings.append("voiced narration_spans source_cut_ids must follow canonical script cut order")
    expected_draft = "\n".join(voiced_span_texts)
    if _as_str(plan.get("continuous_full_draft")).strip() != expected_draft:
        findings.append("audio_story_plan.continuous_full_draft must equal newline-joined voiced span text")
    return findings


def _derive_canonical_audio_story(
    *,
    cut_inventory: list[dict[str, Any]],
    scene_inventory: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    voiced = [
        cut
        for cut in cut_inventory
        if cut["tool"] != "silent" and (str(cut["text"]).strip() or str(cut["tts_text"]).strip())
    ]
    if not voiced:
        raise SystemExit("Cannot derive a full-run audio story because no voiced cut narration was authored.")
    spans: list[dict[str, Any]] = []
    for index, cut in enumerate(voiced, start=1):
        contract_job = _as_str(cut["contract"].get("target_function")).strip()
        if index == len(voiced):
            story_job = contract_job if contract_job in {"payoff", "reaction", "aftertaste"} else "aftertaste"
        elif index == 1:
            story_job = "first_question"
        else:
            story_job = contract_job or "causal_bridge"
        spans.append(
            {
                "span_id": f"ns_{index:03d}",
                "source_cut_ids": [cut["selector"]],
                "story_job": story_job,
                "opened_loop_ids": [],
                "closed_loop_ids": [],
                "text": cut["text"],
                "tts_text": cut["tts_text"] or cut["text"],
                "audio_visual_relation": "causal_alignment",
                "prosody": {
                    "pace": "release" if index == len(voiced) else ("ease" if index == 1 else "steady"),
                    "pause_function": "handoff" if index < len(voiced) else "absorb",
                },
                "tts_generation_group_id": "full_run_01",
            }
        )
    scene_arcs: list[dict[str, Any]] = []
    for index, scene in enumerate(scene_inventory):
        summary = _as_str(scene.get("summary")).strip()
        scene_text = "\n".join(
            str(cut["text"]) for cut in list(scene.get("cuts") or []) if str(cut.get("text") or "").strip()
        )
        anchor = summary or scene_text or f"scene{scene['scene_id']}の視覚的出来事"
        if len(scene_inventory) == 1:
            attention_state = "release"
        elif index == 0:
            attention_state = "orient"
        elif index == len(scene_inventory) - 1:
            attention_state = "release"
        elif index >= max(1, len(scene_inventory) - 2):
            attention_state = "hot"
        else:
            attention_state = "build"
        semantic_load = "high" if len(scene_text) >= 100 else ("medium" if scene_text else "low")
        scene_arcs.append(
            {
                "scene_id": scene["scene_id"],
                "attention_state": attention_state,
                "audience_state_before": f"{anchor}の意味をまだ確定できていない",
                "audience_state_after": f"{anchor}が次の因果へどうつながるかを追える",
                "semantic_load": semantic_load,
                "incoming_causal_question": f"{anchor}は何を変えるのか",
                "outgoing_causal_pressure": f"{anchor}の帰結を次のsceneで確かめる",
            }
        )
    silent_ids = [
        cut["selector"]
        for cut in cut_inventory
        if cut["tool"] == "silent" or not (str(cut["text"]).strip() or str(cut["tts_text"]).strip())
    ]
    plan = {
        "schema_version": "audio_story_plan_v1",
        "authoring_provenance": "derived_legacy_cut_projection",
        "authoring_status": "changes_requested",
        "audience_promise": "冒頭の問いから最後の帰結まで、声で因果と感情の変化を追う。",
        "narrator_bible": {
            "relationship_to_story": "limited_observer",
            "knowledge_boundary": ["script.md と確定済み映像で観客が知れる範囲だけを語る"],
            "emotional_permission": ["人物の迷いと決断に寄り添う"],
            "forbidden_attitudes": ["結末の先取り", "映像にない事実の断定", "人物への嘲笑"],
        },
        "open_loops": [],
        "scene_arcs": scene_arcs,
        "silence_budget": {
            "purpose": "映像だけで読める反応・緊張・余韻を声で埋めない",
            "protected_moments": silent_ids,
            "intentional_silence_cut_ids": silent_ids,
            "principles": ["映像だけで読めるcutは声で重ねない"],
        },
        "continuous_full_draft": "\n".join(str(span["text"]) for span in spans if str(span["text"]).strip()),
    }
    return plan, spans


def _has_revision_aware_narration(node: dict[str, Any]) -> bool:
    audio = node.get("audio") if isinstance(node.get("audio"), dict) else {}
    narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
    revision = narration.get("revision") if isinstance(narration.get("revision"), dict) else {}
    return revision.get("schema_version") == "narration_revision_v1"


def _sync_script_projection(*, run_dir: Path, script_path: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
            "--script",
            str(script_path),
            "--manifest",
            str(run_dir / "video_manifest.md"),
            "--assume-run-lock-held",
        ],
        check=True,
        cwd=REPO_ROOT,
    )


def _merge_scratch_into_script(
    *,
    run_dir: Path,
    script_path: Path,
    by_scene: dict[str, dict[str, dict[str, Any]]],
    audio_story: tuple[dict[str, Any], list[dict[str, Any]]] | None,
    derive_audio_story_if_missing: bool,
    force: bool,
    no_backup: bool,
) -> tuple[list[str], bool] | None:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    script_md = script_path.read_text(encoding="utf-8")
    manifest_path = run_dir / "video_manifest.md"
    state_path = run_dir / "state.txt"
    backup_path = script_path.with_suffix(".md.bak")
    derived_audio_story_path = run_dir / "scratch" / "narration" / "audio_story.yaml"
    transaction_paths = (script_path, manifest_path, state_path, backup_path, derived_audio_story_path)
    transaction_snapshot = {
        path: (path.exists(), path.read_bytes() if path.exists() else b"")
        for path in transaction_paths
    }

    def restore_transaction() -> None:
        for path, (existed, original_bytes) in transaction_snapshot.items():
            if existed:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original_bytes)
            else:
                path.unlink(missing_ok=True)

    try:
        script = yaml.safe_load(extract_yaml_block(script_md))
    except SystemExit:
        return None
    if not isinstance(script, dict) or not isinstance(script.get("scenes"), list):
        return None
    changed_scenes: list[str] = []
    full_run_changed = False
    for scene in script["scenes"]:
        if not isinstance(scene, dict) or is_non_renderable_manifest_node(scene):
            continue
        scene_id = _normalized_id(scene.get("scene_id"))
        if scene_id is None or scene_id not in by_scene:
            continue
        cuts = scene.get("cuts")
        if not isinstance(cuts, list):
            continue
        changed = False
        for cut in cuts:
            if not isinstance(cut, dict) or is_non_renderable_manifest_node(cut):
                continue
            cut_id = _normalized_id(cut.get("cut_id"))
            if cut_id is None or cut_id not in by_scene[scene_id]:
                continue
            authoring = cut.get("narration_authoring") if isinstance(cut.get("narration_authoring"), dict) else {}
            if str(authoring.get("status") or "").strip() in {"human_locked", "reviewed", "silent"}:
                continue
            payload = by_scene[scene_id][cut_id]
            next_text = _as_str(payload.get("text")).strip()
            next_tts = _as_str(payload.get("tts_text")).strip()
            current_text = _as_str(cut.get("narration")).strip()
            if current_text and not force:
                next_text = current_text
            field_changes = {
                "narration": next_text,
                "tts_text": next_tts,
                "elevenlabs_prompt": dict(payload.get("prompt") or {}),
                "narration_contract": _normalize_contract(payload.get("contract")),
            }
            if any(cut.get(key) != value for key, value in field_changes.items()):
                cut.update(field_changes)
                preserved_authoring = {
                    key: value
                    for key, value in authoring.items()
                    if key
                    not in {
                        "semantic_revision",
                        "semantic_hash",
                        "tts_revision",
                        "tts_request_hash",
                        "updated_at",
                        "source",
                    }
                }
                cut["narration_authoring"] = {
                    **preserved_authoring,
                    "schema_version": "narration_authoring_v1",
                    "status": "draft",
                    "source": "multiagent_scratch_merge",
                    "updated_at": now_iso(),
                }
                human_review = cut.get("human_review") if isinstance(cut.get("human_review"), dict) else {}
                human_review.update(
                    {
                        "status": "pending",
                        "approved_narration": "",
                        "approved_tts_text": "",
                        "approved_at": "",
                    }
                )
                cut["human_review"] = human_review
                changed = True
        if changed:
            changed_scenes.append(scene_id)
    cut_inventory, scene_inventory = _script_narration_inventory(script)
    derived_audio_story = False
    if audio_story is None and derive_audio_story_if_missing:
        audio_story = _derive_canonical_audio_story(
            cut_inventory=cut_inventory,
            scene_inventory=scene_inventory,
        )
        derived_audio_story = True
    if audio_story is not None:
        plan, spans = audio_story
        canonical_findings = _validate_canonical_audio_story(
            plan=plan,
            spans=spans,
            cut_inventory=cut_inventory,
        )
        if canonical_findings:
            raise SystemExit("audio_story.yaml is inconsistent with cut narration: " + "; ".join(canonical_findings))
        if script.get("audio_story_plan") != plan:
            script["audio_story_plan"] = plan
            full_run_changed = True
        if script.get("narration_spans") != spans:
            script["narration_spans"] = spans
            full_run_changed = True
    if not changed_scenes and not full_run_changed:
        try:
            _sync_script_projection(run_dir=run_dir, script_path=script_path)
        except Exception:
            restore_transaction()
            raise
        return [], False
    new_yaml = yaml.safe_dump(script, sort_keys=False, allow_unicode=True)
    try:
        if not no_backup:
            shutil.copy2(script_path, backup_path)
        if derived_audio_story and audio_story is not None:
            plan, spans = audio_story
            derived_audio_story_path.write_text(
                yaml.safe_dump(
                    {
                        "schema_version": "narration_audio_story_scratch_v1",
                        "audio_story_plan": plan,
                        "narration_spans": spans,
                        "locked_cut_inputs": [
                            {
                                "selector": cut["selector"],
                                "authoring_status": cut["authoring_status"],
                                "text": cut["text"],
                                "tts_text": cut["tts_text"] or cut["text"],
                                "read_only": True,
                            }
                            for cut in cut_inventory
                            if cut["authoring_status"] in {"human_locked", "reviewed", "silent"}
                        ],
                        "notes": [
                            "legacy runの初回mergeでcut原稿からcanonical projectionとして生成。",
                            "次回以降はAudio Story Directorが全編品質をreviewし、暗黙の再生成はしない。",
                        ],
                    },
                    sort_keys=False,
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )
        script_path.write_text(replace_yaml_block(script_md, new_yaml), encoding="utf-8")
        _sync_script_projection(run_dir=run_dir, script_path=script_path)
    except Exception:
        restore_transaction()
        raise
    return changed_scenes, full_run_changed


def _main_locked(args: argparse.Namespace, run_dir: Path) -> None:
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    scratch_dir = run_dir / "scratch" / "narration"
    if not scratch_dir.exists():
        raise SystemExit(f"Scratch not found: {scratch_dir} (run toc-immersive-narration-multiagent.py first)")

    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")

    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    manifest = yaml.safe_load(y)
    if not isinstance(manifest, dict):
        raise SystemExit("Manifest YAML must be a mapping at the root.")
    raw_scenes = manifest.get("scenes")
    if not isinstance(raw_scenes, list):
        raise SystemExit("Manifest YAML scenes must be a list.")

    scratch_files = sorted(scratch_dir.glob("scene*.yaml"))
    if not scratch_files:
        raise SystemExit(f"No scratch files found in: {scratch_dir}")

    available_story_scene_ids = {
        normalized
        for scene_id in story_scene_ids(raw_scenes)
        if (normalized := _normalized_id(scene_id)) is not None
    }
    by_scene: dict[str, dict[str, dict[str, Any]]] = {}
    for f in scratch_files:
        parsed = _load_scratch_file(f)
        if parsed is None:
            continue
        sid, cuts = parsed
        if sid not in available_story_scene_ids:
            continue
        by_scene[sid] = cuts

    revision_aware = any(
        isinstance(cut, dict)
        and not is_non_renderable_manifest_node(cut)
        and _has_revision_aware_narration(cut)
        for scene in raw_scenes
        if isinstance(scene, dict) and not is_non_renderable_manifest_node(scene)
        for cut in (scene.get("cuts") if isinstance(scene.get("cuts"), list) else [scene])
    )
    script_path = run_dir / "script.md"
    audio_story = (
        _load_audio_story_scratch(scratch_dir / "audio_story.yaml")
        if script_path.is_file()
        else None
    )
    script_merge_result = (
        _merge_scratch_into_script(
            run_dir=run_dir,
            script_path=script_path,
            by_scene=by_scene,
            audio_story=audio_story,
            derive_audio_story_if_missing=revision_aware,
            force=args.force,
            no_backup=args.no_backup,
        )
        if script_path.is_file()
        else None
    )
    if script_merge_result is not None:
        changed_scenes, full_run_changed = script_merge_result
        if not changed_scenes and not full_run_changed:
            print("No script changes; synchronized the manifest projection.")
            return
        state_path = run_dir / "state.txt"
        if state_path.exists():
            append_state_block(
                state_path,
                {
                    "timestamp": now_iso(),
                    "runtime.stage": "immersive_narration_script_merged_and_synced",
                    "immersive.narration.merged_scenes": ",".join(
                        str(scene_id) for scene_id in sorted(set(changed_scenes), key=dotted_id_sort_key)
                    ),
                    "immersive.narration.audio_story_updated": str(full_run_changed).lower(),
                    "artifact.narration_source_of_truth": "script.md",
                },
            )
        print(
            "Merged scenes:",
            ",".join(str(scene_id) for scene_id in sorted(set(changed_scenes), key=dotted_id_sort_key)) or "none",
        )
        print("Updated full-run audio story:", str(full_run_changed).lower())
        print("Updated script source of truth:", script_path)
        print("Synced manifest projection:", manifest_path)
        return

    if revision_aware:
        raise SystemExit(
            "revision-aware narration cannot be merged directly into video_manifest.md; "
            "materialize structured script.md first, then rerun this command"
        )

    changed_scenes: list[str] = []
    for s in raw_scenes:
        if not isinstance(s, dict) or is_non_renderable_manifest_node(s):
            continue
        sid = _normalized_id(s.get("scene_id"))
        if sid is None or sid not in by_scene:
            continue

        raw_cuts = s.get("cuts")
        if isinstance(raw_cuts, list) and raw_cuts:
            wanted = by_scene[sid]
            if not wanted:
                continue
            changed_any = False
            for cut in raw_cuts:
                if not isinstance(cut, dict) or is_non_renderable_manifest_node(cut):
                    continue
                cid = _normalized_id(cut.get("cut_id"))
                if cid is None or cid not in wanted:
                    continue
                narration = _ensure_audio_narration(cut, scene_id=sid, cut_id=cid)
                if _as_str(narration.get("authoring_status")).strip() in {"human_locked", "reviewed", "silent"}:
                    continue
                prev = _as_str(narration.get("text")).strip()
                prev_tts = _as_str(narration.get("tts_text")).strip()
                payload = wanted[cid]
                nxt = _as_str(payload.get("text")).strip()
                nxt_tts = _as_str(payload.get("tts_text")).strip()
                contract = _normalize_contract(payload.get("contract"))
                if prev and not args.force:
                    if prev_tts != nxt_tts and nxt_tts:
                        narration["tts_text"] = nxt_tts
                        changed_any = True
                    if contract != _normalize_contract(narration.get("contract") if isinstance(narration.get("contract"), dict) else {}):
                        narration["contract"] = contract
                        changed_any = True
                    continue
                if prev != nxt:
                    narration["text"] = nxt
                    changed_any = True
                if prev_tts != nxt_tts:
                    narration["tts_text"] = nxt_tts
                    changed_any = True
                if contract != _normalize_contract(narration.get("contract") if isinstance(narration.get("contract"), dict) else {}):
                    narration["contract"] = contract
                    changed_any = True
            if changed_any:
                changed_scenes.append(sid)
            continue

        # Scene-level narration (no cuts).
        wanted = by_scene[sid]
        if not wanted:
            continue
        if len(wanted) != 1 or "1" not in wanted:
            raise SystemExit(f"scene{sid}: no cuts in manifest; scratch must have exactly one cut_id: 1")
        narration = _ensure_audio_narration(s, scene_id=sid, cut_id=None)
        if _as_str(narration.get("authoring_status")).strip() in {"human_locked", "reviewed", "silent"}:
            continue
        prev = _as_str(narration.get("text")).strip()
        prev_tts = _as_str(narration.get("tts_text")).strip()
        payload = wanted["1"]
        nxt = _as_str(payload.get("text")).strip()
        nxt_tts = _as_str(payload.get("tts_text")).strip()
        contract = _normalize_contract(payload.get("contract"))
        if prev and not args.force:
            if prev_tts != nxt_tts and nxt_tts:
                narration["tts_text"] = nxt_tts
                changed_scenes.append(sid)
            if contract != _normalize_contract(narration.get("contract") if isinstance(narration.get("contract"), dict) else {}):
                narration["contract"] = contract
                changed_scenes.append(sid)
            continue
        if prev != nxt:
            narration["text"] = nxt
            changed_scenes.append(sid)
        if prev_tts != nxt_tts:
            narration["tts_text"] = nxt_tts
            if sid not in changed_scenes:
                changed_scenes.append(sid)
        if contract != _normalize_contract(narration.get("contract") if isinstance(narration.get("contract"), dict) else {}):
            narration["contract"] = contract
            if sid not in changed_scenes:
                changed_scenes.append(sid)

    if not changed_scenes:
        print("No scenes changed.")
        return

    new_yaml = yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True)
    if not args.no_backup:
        backup = manifest_path.with_suffix(".md.bak")
        shutil.copy2(manifest_path, backup)
    manifest_path.write_text(replace_yaml_block(md, new_yaml), encoding="utf-8")

    state_path = run_dir / "state.txt"
    if state_path.exists():
        append_state_block(
            state_path,
            {
                "timestamp": now_iso(),
                "runtime.stage": "immersive_narration_merged",
                "immersive.narration.merged_scenes": ",".join(
                    str(s) for s in sorted(set(changed_scenes), key=dotted_id_sort_key)
                ),
            },
        )

    print(
        "Merged scenes:",
        ",".join(str(s) for s in sorted(set(changed_scenes), key=dotted_id_sort_key)),
    )
    print("Updated manifest:", manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge full-run + scene narration scratch into script.md and its manifest projection (single-writer)."
    )
    parser.add_argument(
        "--run-dir",
        required=True,
        help="Immersive run dir containing script.md, video_manifest.md, and scratch/narration/*.yaml",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing narration text even if non-empty.")
    parser.add_argument("--no-backup", action="store_true", help="Do not create script.md/video_manifest.md.bak before writing.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    with sync_file_lock(run_dir / ".locks" / "run_artifacts.lock"):
        _main_locked(args, run_dir)


if __name__ == "__main__":
    main()
