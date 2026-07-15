#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

try:
    import yaml  # type: ignore[import-not-found]
except ModuleNotFoundError:  # pragma: no cover
    yaml = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.immersive_manifest import (
    default_story_scene_start,
    dotted_id_slug,
    dotted_id_sort_key,
    is_non_renderable_manifest_node,
    make_scene_cut_selector,
    normalize_dotted_id,
    story_scene_ids,
)


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def extract_yaml_block(text: str) -> str:
    m = re.search(r"```yaml\s*\n(.*?)\n```", text, flags=re.DOTALL)
    if not m:
        raise SystemExit("No ```yaml ... ``` block found in manifest markdown.")
    return m.group(1)


def _normalized_id(value: object) -> str | None:
    return normalize_dotted_id(value)


def _manifest_id_value(value: object) -> int | str:
    normalized = _normalized_id(value)
    if normalized is None:
        raise ValueError(f"invalid dotted numeric id: {value!r}")
    return int(normalized) if normalized.isdigit() else normalized


def _scene_scratch_path(scratch_dir: Path, scene_id: object) -> Path:
    normalized = _normalized_id(scene_id)
    if normalized is None:
        raise ValueError(f"invalid scene id: {scene_id!r}")
    filename_id = f"{int(normalized):02d}" if normalized.isdigit() else dotted_id_slug(normalized)
    return scratch_dir / f"scene{filename_id}.yaml"


def _active_manifest_cuts(scene: dict) -> list[dict]:
    raw_cuts = scene.get("cuts") if isinstance(scene.get("cuts"), list) else []
    return [
        cut
        for cut in raw_cuts
        if isinstance(cut, dict)
        and not is_non_renderable_manifest_node(cut)
        and _normalized_id(cut.get("cut_id")) is not None
    ]


def _load_scene_ids(manifest_path: Path) -> list[dict]:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    md = manifest_path.read_text(encoding="utf-8")
    y = extract_yaml_block(md)
    data = yaml.safe_load(y)
    if not isinstance(data, dict):
        raise SystemExit("Manifest YAML must be a mapping at the root.")
    raw_scenes = data.get("scenes") or []
    if not isinstance(raw_scenes, list):
        raise SystemExit("Manifest YAML scenes must be a list.")
    return [scene for scene in raw_scenes if isinstance(scene, dict)]


def _parse_scene_ids(scene_ids_csv: str | None) -> list[str] | None:
    if not scene_ids_csv:
        return None
    out: list[str] = []
    for raw in scene_ids_csv.split(","):
        s = raw.strip()
        if not s:
            continue
        scene_id = _normalized_id(s)
        if scene_id is None:
            raise SystemExit(f"Invalid dotted numeric scene id: {s!r}")
        out.append(scene_id)
    return out or None


def _audio_story_scratch(scene_ids: list[str], locked_cut_inputs: list[dict]) -> dict:
    return {
        "schema_version": "narration_audio_story_scratch_v1",
        "audio_story_plan": {
            "schema_version": "audio_story_plan_v1",
            "authoring_provenance": "audio_story_director",
            "authoring_status": "draft",
            "audience_promise": "",
            "narrator_bible": {
                "relationship_to_story": "",
                "knowledge_boundary": [],
                "emotional_permission": [],
                "forbidden_attitudes": [],
            },
            "open_loops": [],
            "scene_arcs": [
                {
                    "scene_id": _manifest_id_value(scene_id),
                    "attention_state": "",
                    "audience_state_before": "",
                    "audience_state_after": "",
                    "semantic_load": "",
                    "incoming_causal_question": "",
                    "outgoing_causal_pressure": "",
                }
                for scene_id in scene_ids
            ],
            "silence_budget": {
                "purpose": "",
                "protected_moments": [],
                "intentional_silence_cut_ids": [],
                "principles": [],
            },
            "continuous_full_draft": "",
        },
        "narration_spans": [],
        "locked_cut_inputs": locked_cut_inputs,
        "notes": [
            "先に audio_story_plan と continuous_full_draft を全編通して完成させ、その後で narration_spans に分割する。",
            "continuous_full_draft は cut 境界や制作メタを含めず、最初から最後まで声として通読できる本文にする。",
            "各 voiced cut は原則ちょうど1つの voiced span から参照し、span本文はsource_cut_ids順のcut原稿を改行連結した値にする。",
            "continuous_full_draft はvoiced spanのtextをspan順に改行連結した値にする。",
            "最後の span の story_job は payoff / reaction / aftertaste のいずれかにする。",
            "frontend で human_locked の文面は上書きせず、全編設計側をその確定文面へ合わせる。",
        ],
    }


def _cut_audio_narration(cut: dict) -> dict:
    audio = cut.get("audio") if isinstance(cut.get("audio"), dict) else {}
    narration = audio.get("narration") if isinstance(audio.get("narration"), dict) else {}
    return narration


def _authoring_status(narration: dict) -> str:
    return str(narration.get("authoring_status") or "missing").strip().lower()


def _locked_cut_inventory(manifest_scenes: list[dict], targets: list[str]) -> list[dict]:
    target_ids = set(targets)
    locked: list[dict] = []
    for scene in manifest_scenes:
        if not isinstance(scene, dict) or is_non_renderable_manifest_node(scene):
            continue
        scene_id = _normalized_id(scene.get("scene_id"))
        if scene_id is None or scene_id not in target_ids:
            continue
        for cut in _active_manifest_cuts(scene):
            cut_id = _normalized_id(cut.get("cut_id"))
            assert cut_id is not None
            narration = _cut_audio_narration(cut)
            status = _authoring_status(narration)
            if status not in {"human_locked", "reviewed", "silent"}:
                continue
            text = str(narration.get("text") or "").strip()
            tts_text = str(narration.get("tts_text") or text).strip()
            locked.append(
                {
                    "selector": make_scene_cut_selector(scene_id, cut_id),
                    "authoring_status": status,
                    "text": text,
                    "tts_text": tts_text,
                    "read_only": True,
                }
            )
    return locked


def _scene_cut_scratch(cut_id: str, manifest_cut: dict | None) -> dict:
    manifest_cut = manifest_cut or {}
    narration = _cut_audio_narration(manifest_cut)
    status = _authoring_status(narration)
    locked = status in {"human_locked", "reviewed", "silent"}
    text = str(narration.get("text") or "").strip()
    tts_text = str(narration.get("tts_text") or text).strip()
    return {
        "cut_id": _manifest_id_value(cut_id),
        "authoring_status": status,
        "locked": locked,
        "read_only": locked,
        "target_function": "",
        "must_cover": [],
        "must_avoid": [],
        "done_when": [],
        "spoken_context": "",
        "voice_tags": [],
        "spoken_body": "",
        "stability_profile": "",
        "narration_text": text,
        "tts_text": tts_text,
    }


def _refresh_scene_scratch(path: Path, manifest_scene: dict) -> None:
    if yaml is None:
        raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("cuts"), list):
        raise SystemExit(f"Scene narration scratch must contain a cuts list: {path}")
    existing = {
        cut_id: cut
        for cut in data["cuts"]
        if isinstance(cut, dict) and (cut_id := _normalized_id(cut.get("cut_id"))) is not None
    }
    changed = False
    projected_cuts: list[dict] = []
    for manifest_cut in _active_manifest_cuts(manifest_scene):
        cut_id = _normalized_id(manifest_cut.get("cut_id"))
        assert cut_id is not None
        seed = _scene_cut_scratch(cut_id, manifest_cut)
        current = existing.get(cut_id)
        if current is None:
            current = seed
            changed = True
        else:
            status_projection = {
                "cut_id": seed["cut_id"],
                "authoring_status": seed["authoring_status"],
                "locked": seed["locked"],
                "read_only": seed["read_only"],
            }
            if seed["locked"]:
                status_projection.update(
                    {
                        "narration_text": seed["narration_text"],
                        "tts_text": seed["tts_text"],
                    }
                )
            if any(current.get(key) != value for key, value in status_projection.items()):
                current.update(status_projection)
                changed = True
        projected_cuts.append(current)
    projected_cuts.sort(key=lambda cut: dotted_id_sort_key(cut.get("cut_id")))
    if data["cuts"] != projected_cuts:
        data["cuts"] = projected_cuts
        changed = True
    if changed:
        path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _nested_mapping(node: dict, *keys: str) -> dict:
    current: object = node
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _prompt_text(manifest_scenes: list[dict], targets: list[str]) -> str:
    target_ids = set(targets)
    lines = [
        "# p700 Full-run Audio Story Authoring Prompt",
        "",
        "あなたは Audio Story Director 兼 single-writer です。cut別の短文を先に量産せず、全編の声を一つの物語として設計してください。",
        "",
        "## Authoring order（順序を変えない）",
        "",
        "1. `audio_story.yaml.audio_story_plan` に audience promise、narrator bible、open loop/payoff、全sceneのattention arc、silence budgetを記入する。",
        "2. `continuous_full_draft` に、cut境界のない全編のspoken Japaneseを書く。映像説明の羅列、制作メタ、未回収の問いを残さない。",
        "3. 全編を通読し、冒頭の視聴継続理由、attentionの再点火、語り手人格、情報負荷、scene間因果、映像との役割分担、payoff後の余韻を直す。",
        "4. 通し原稿を意味・演技単位の `narration_spans[]` へ順番どおり分割し、下の正規selectorだけを `source_cut_ids` に使う。1 spanは複数cutを跨いでよい。",
        "5. spanを根拠に `sceneXX.yaml.cuts[]` の公開用 `narration_text` と最終TTS用 `tts_text` を作る。映像が担うcutは無音にできる。",
        "6. 全編設計とcanonical projectionが一致したら `authoring_provenance: audio_story_director` / `authoring_status: authored` にする。draftのままmergeしない。",
        "7. single-writer が merge を実行し、`script.md` を正本として manifest へ同期する。",
        "",
        "## Blocking rules",
        "",
        "- 空文字、TODO、選択肢のままのenum、仮文を残さない。",
        "- 全sceneに `scene_arcs` を1件ずつ置き、attention_state / audience_state_before / audience_state_after / semantic_load を具体化する。",
        "- voiced spanは text / tts_text / tts_generation_group_id / source_cut_ids を必須とする。",
        "- 各voiced cutは、原則ちょうど1つのvoiced spanへanchorする。",
        "- 各voiced spanの `text` / `tts_text` は、`source_cut_ids` の順でnon-empty cut原稿を改行連結した値と完全一致させる。",
        "- `continuous_full_draft` はvoiced spanの `text`をspan順に改行連結した値と完全一致させる。",
        "- 同一ナレーションのcut間コピーを避ける。",
        "- 冒頭で audience_promise を具体的な問い・危機・違和感として立ち上げ、途中のsceneで進展・反転・再点火を与える。煽り文句だけのhookは禁止する。",
        "- narrationはvisible factの字幕化を避け、因果・内面・時間・意味・対比を足す。revealや人物のreactionを映像より先に説明しない。",
        "- narrator_bibleのknowledge_boundary / emotional_permission / forbidden_attitudesを全spanで守り、sceneごとに別人格へ変えない。",
        "- 高密度区間の後には理解・感情を受け取る短い呼吸または意図的な無音を置き、同じ強度を連打しない。",
        "- open loopを設けた場合は opened_at / payoff_at と、対応する span の opened_loop_ids / closed_loop_ids を一致させる。",
        "- 最終spanは payoff / reaction / aftertaste のいずれかにする。",
        "- `narration_authoring.status` が human_locked / reviewed / silent のcutは上書きしない。",
        "",
        "## Canonical scene/cut inventory",
        "",
    ]
    for scene in manifest_scenes:
        if not isinstance(scene, dict) or is_non_renderable_manifest_node(scene):
            continue
        scene_id = _normalized_id(scene.get("scene_id"))
        if scene_id is None or scene_id not in target_ids:
            continue
        scene_summary = str(scene.get("scene_summary") or scene.get("story_visual") or "").strip()
        lines.append(f"### scene{scene_id}: {scene_summary or '(summary missing)'}")
        lines.append("")
        for cut in _active_manifest_cuts(scene):
            cut_id = _normalized_id(cut.get("cut_id"))
            assert cut_id is not None
            selector = make_scene_cut_selector(scene_id, cut_id)
            contract = cut.get("cut_contract") if isinstance(cut.get("cut_contract"), dict) else {}
            if not contract and isinstance(cut.get("scene_contract"), dict):
                contract = cut["scene_contract"]
            viewer = contract.get("viewer_contract") if isinstance(contract.get("viewer_contract"), dict) else {}
            narration_contract = contract.get("narration_contract") if isinstance(contract.get("narration_contract"), dict) else {}
            story_role = (
                narration_contract.get("story_role")
                if isinstance(narration_contract.get("story_role"), dict)
                else {}
            )
            visual = str(
                cut.get("visual_beat")
                or viewer.get("visual_proof")
                or viewer.get("target_beat")
                or ""
            ).strip()
            target_beat = str(viewer.get("target_beat") or cut.get("target_beat") or "").strip()
            voice_function = str(story_role.get("voice_function") or narration_contract.get("role") or "").strip()
            duration = _nested_mapping(cut, "video_generation").get("duration_seconds")
            audio = _nested_mapping(cut, "audio", "narration")
            authoring_status = str(
                audio.get("authoring_status")
                or _nested_mapping(audio, "revision").get("authoring_status")
                or "missing"
            ).strip()
            entry_lines = [
                f"- `{selector}`",
                f"  - target beat: {target_beat or '(missing)'}",
                f"  - visible beat: {visual or '(missing)'}",
                f"  - voice function: {voice_function or '(derive from story role)'}",
                f"  - target duration: {duration if duration is not None else '(missing)'} seconds",
                f"  - current authoring status: {authoring_status}",
            ]
            if authoring_status in {"human_locked", "reviewed", "silent"}:
                locked_text = str(audio.get("text") or "").strip()
                locked_tts = str(audio.get("tts_text") or locked_text).strip()
                entry_lines.extend(
                    [
                        "  - read only: true（変更禁止。global plan/spanをこの確定値へ合わせる）",
                        f"  - locked text: {locked_text!r}",
                        f"  - locked tts_text: {locked_tts!r}",
                    ]
                )
            lines.extend(entry_lines)
        lines.append("")
    lines.extend(
        [
            "## Required outputs",
            "",
            "- `scratch/narration/audio_story.yaml`: completed audio_story_plan + continuous_full_draft + narration_spans",
            "- `scratch/narration/sceneXX.yaml`: spanに基づくcut projection（公開文 / TTS文 / delivery / contract）",
            "- merge後の `script.md`: 上記全編成果物とcut原稿を持つ唯一の言語正本",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare per-scene narration scratch files for immersive manifests (multi-agent safe).")
    parser.add_argument("--run-dir", required=True, help="Existing immersive run dir (contains video_manifest.md).")
    parser.add_argument("--scene-ids", default=None, help='Comma-separated scene ids to prepare (default: auto from manifest).')
    parser.add_argument(
        "--start-scene-id",
        default=None,
        help="Prepare scenes with id >= this (default: auto-detect from manifest story scenes).",
    )
    parser.add_argument("--min-cuts", type=int, default=3, help="Default number of cuts per scene (used only when scratch is created).")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    manifest_path = run_dir / "video_manifest.md"
    if not manifest_path.exists():
        raise SystemExit(f"Manifest not found: {manifest_path}")

    manifest_scenes = _load_scene_ids(manifest_path)
    available_story_scene_ids = {
        normalized
        for scene_id in story_scene_ids(manifest_scenes)
        if (normalized := _normalized_id(scene_id)) is not None
    }
    full_run_scene_ids = sorted(available_story_scene_ids, key=dotted_id_sort_key)
    requested = _parse_scene_ids(args.scene_ids)
    scene_ids = requested if requested is not None else full_run_scene_ids
    start_scene_id = _normalized_id(
        args.start_scene_id
        if args.start_scene_id is not None
        else default_story_scene_start(manifest_scenes)
    )
    if start_scene_id is None:
        raise SystemExit(f"Invalid --start-scene-id: {args.start_scene_id!r}")
    targets = sorted(
        {
            sid
            for sid in scene_ids
            if sid in available_story_scene_ids
            and dotted_id_sort_key(sid) >= dotted_id_sort_key(start_scene_id)
        },
        key=dotted_id_sort_key,
    )
    if not targets:
        raise SystemExit("No target scenes found. Check --scene-ids / --start-scene-id.")

    scratch_dir = run_dir / "scratch" / "narration"
    scratch_dir.mkdir(parents=True, exist_ok=True)

    locked_cut_inputs = _locked_cut_inventory(manifest_scenes, full_run_scene_ids)
    audio_story_path = scratch_dir / "audio_story.yaml"
    if not audio_story_path.exists():
        if yaml is None:
            raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
        audio_story_path.write_text(
            yaml.safe_dump(
                _audio_story_scratch(full_run_scene_ids, locked_cut_inputs),
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
    else:
        if yaml is None:
            raise SystemExit("PyYAML is required. Install with: pip install pyyaml")
        existing_audio_story = yaml.safe_load(audio_story_path.read_text(encoding="utf-8"))
        if not isinstance(existing_audio_story, dict):
            raise SystemExit(f"Full-run audio story scratch must be a mapping: {audio_story_path}")
        if existing_audio_story.get("locked_cut_inputs") != locked_cut_inputs:
            existing_audio_story["locked_cut_inputs"] = locked_cut_inputs
            audio_story_path.write_text(
                yaml.safe_dump(existing_audio_story, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
    (scratch_dir / "authoring_prompt.md").write_text(
        _prompt_text(manifest_scenes, full_run_scene_ids),
        encoding="utf-8",
    )

    scene_by_id = {
        scene_id: scene
        for scene in manifest_scenes
        if isinstance(scene, dict)
        and not is_non_renderable_manifest_node(scene)
        and (scene_id := _normalized_id(scene.get("scene_id"))) is not None
    }
    for sid in targets:
        p = _scene_scratch_path(scratch_dir, sid)
        manifest_scene = scene_by_id.get(sid, {})
        if p.exists():
            _refresh_scene_scratch(p, manifest_scene)
            continue
        manifest_cuts_by_id = {
            cut_id: cut
            for cut in _active_manifest_cuts(manifest_scene)
            if (cut_id := _normalized_id(cut.get("cut_id"))) is not None
        }
        manifest_cut_ids = [
            cut_id
            for cut in _active_manifest_cuts(manifest_scene)
            if (cut_id := _normalized_id(cut.get("cut_id"))) is not None
        ]
        cut_ids = manifest_cut_ids or [str(index) for index in range(1, int(args.min_cuts) + 1)]
        skeleton = {
            "scene_id": _manifest_id_value(sid),
            "cuts": [
                _scene_cut_scratch(i, manifest_cuts_by_id.get(i))
                for i in cut_ids
            ],
            "notes": [
                "narration_text は物語用、tts_text は ElevenLabs v3 に送る最終文字列として使う。",
                "spoken_context / voice_tags / spoken_body / stability_profile を先に書き、tts_text はその完成形を置く。",
                "tts_text は ひらがな寄せを基本にしつつ、[] の audio tag を許可する。TODO/メタ情報は書かない。",
                "先に target_function / must_cover / must_avoid / done_when を埋め、done 条件を明確にする。",
                "cutは映像単位、narration spanは文章・演技単位。scene内で通して読める流れを優先し、無音cutや複数cutをまたぐspanを許可する。",
            ],
        }
        if yaml is None:
            lines: list[str] = []
            lines.append(f"scene_id: {_manifest_id_value(sid)}")
            lines.append("cuts:")
            for i in cut_ids:
                lines += [
                    f"  - cut_id: {i}",
                    "    target_function: \"\"",
                    "    must_cover: []",
                    "    must_avoid: []",
                    "    done_when: []",
                    "    spoken_context: \"\"",
                    "    voice_tags: []",
                    "    spoken_body: \"\"",
                    "    stability_profile: \"\"",
                    "    narration_text: \"\"",
                    "    tts_text: \"\"",
                ]
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            p.write_text(yaml.safe_dump(skeleton, sort_keys=False, allow_unicode=True), encoding="utf-8")

    print(f"Run dir: {run_dir}")
    print(f"Prepared scratch: {scratch_dir}")
    print(f"Full-run audio story: {audio_story_path}")
    print(f"Authoring prompt: {scratch_dir / 'authoring_prompt.md'}")
    print("Targets:", ",".join(str(s) for s in targets))
    print("次（並列）: scene担当は scratch/narration/sceneXX.yaml を編集する。")
    print("次（single-writer）:")
    print(f'  python scripts/ai/merge-immersive-narration.py --run-dir "{run_dir}"')


if __name__ == "__main__":
    main()
