import importlib.util
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from toc.harness import load_structured_document
from toc.narration_arc import validate_audio_story_contract
from toc.runtime_locks import sync_file_lock

REPO_ROOT = Path(__file__).resolve().parents[1]
MERGE_SCRIPT_PATH = REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"
MERGE_SPEC = importlib.util.spec_from_file_location("merge_immersive_narration_transaction", MERGE_SCRIPT_PATH)
assert MERGE_SPEC and MERGE_SPEC.loader
MERGE_MODULE = importlib.util.module_from_spec(MERGE_SPEC)
sys.modules[MERGE_SPEC.name] = MERGE_MODULE
MERGE_SPEC.loader.exec_module(MERGE_MODULE)


class TestImmersiveNarrationMultiagent(unittest.TestCase):
    def test_merge_sync_failure_rolls_back_script_manifest_and_state_byte_exactly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_merge_transaction_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"
            state_path = run_dir / "state.txt"
            (run_dir / "scratch" / "narration").mkdir(parents=True)
            script_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        narration: ""
        tts_text: ""
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        audio:
          narration: {text: "", tts_text: ""}
```
""",
                encoding="utf-8",
            )
            state_path.write_bytes(b"original-state\n")
            before = {
                path: path.read_bytes()
                for path in (script_path, manifest_path, state_path)
            }

            original_sync = MERGE_MODULE._sync_script_projection

            def fail_after_partial_projection(*, run_dir: Path, script_path: Path) -> None:
                del script_path
                (run_dir / "video_manifest.md").write_bytes(b"partially-synced-manifest")
                (run_dir / "state.txt").write_bytes(b"partially-synced-state")
                raise RuntimeError("simulated projection failure")

            MERGE_MODULE._sync_script_projection = fail_after_partial_projection
            try:
                with self.assertRaisesRegex(RuntimeError, "projection failure"):
                    MERGE_MODULE._merge_scratch_into_script(
                        run_dir=run_dir,
                        script_path=script_path,
                        by_scene={
                            "10": {
                                "1": {
                                    "text": "新しい語りです。",
                                    "tts_text": "あたらしい かたりです。",
                                    "prompt": {},
                                    "contract": {},
                                }
                            }
                        },
                        audio_story=None,
                        derive_audio_story_if_missing=False,
                        force=True,
                        no_backup=True,
                    )
            finally:
                MERGE_MODULE._sync_script_projection = original_sync

            for path, expected in before.items():
                self.assertEqual(path.read_bytes(), expected, path.name)

    def test_prepare_uses_active_inventory_and_preserves_dotted_ids(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_dotted_prepare_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(
                """```yaml
scenes:
  - scene_id: 0
    kind: character_reference
  - scene_id: 5
    status: deleted
  - scene_id: 7
    scene_kind: location_reference
  - scene_id: 10
    cuts:
      - cut_id: 1
        status: deleted
      - cut_id: 1.1
        visual_beat: "封印のひびが光る"
      - cut_id: 2
        kind: object_reference
      - cut_id: 3
        image_generation:
          output: assets/characters/reference-cut.png
  - scene_id: 10.1
    cuts:
      - cut_id: 1
        visual_beat: "光の先へ踏み出す"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--min-cuts",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            import yaml

            scratch_dir = run_dir / "scratch" / "narration"
            audio_story = yaml.safe_load((scratch_dir / "audio_story.yaml").read_text(encoding="utf-8"))
            scene10 = yaml.safe_load((scratch_dir / "scene10.yaml").read_text(encoding="utf-8"))
            scene10_1 = yaml.safe_load((scratch_dir / "scene10_1.yaml").read_text(encoding="utf-8"))
            prompt = (scratch_dir / "authoring_prompt.md").read_text(encoding="utf-8")

            self.assertEqual(
                [arc["scene_id"] for arc in audio_story["audio_story_plan"]["scene_arcs"]],
                [10, "10.1"],
            )
            self.assertEqual([cut["cut_id"] for cut in scene10["cuts"]], ["1.1"])
            self.assertEqual([cut["cut_id"] for cut in scene10_1["cuts"]], [1])
            self.assertIn("scene10_cut1.1", prompt)
            self.assertIn("scene10.1_cut1", prompt)
            self.assertNotIn("scene5", prompt)
            self.assertNotIn("scene7", prompt)
            self.assertNotIn("scene10_cut1`", prompt)
            self.assertNotIn("scene10_cut2", prompt)
            self.assertNotIn("scene10_cut3", prompt)

    def test_legacy_prepare_merge_and_arc_keep_dotted_cut_selector(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_dotted_merge_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        status: deleted
        audio:
          narration: {text: "", tts_text: ""}
      - cut_id: 1.1
        audio:
          narration: {text: "", tts_text: "", tool: elevenlabs}
      - cut_id: 2
        kind: location_reference
        audio:
          narration: {text: "", tts_text: ""}
```
""",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--scene-ids",
                    "10",
                    "--min-cuts",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            scratch_path = run_dir / "scratch" / "narration" / "scene10.yaml"
            import yaml

            scratch = yaml.safe_load(scratch_path.read_text(encoding="utf-8"))
            self.assertEqual([cut["cut_id"] for cut in scratch["cuts"]], ["1.1"])
            scratch["cuts"][0]["narration_text"] = "ひびの向こうで、約束が目を覚まします。"
            scratch["cuts"][0]["tts_text"] = "ひびの むこうで、やくそくが めを さまします。"
            scratch_path.write_text(
                yaml.safe_dump(scratch, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )

            merged = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                    "--no-backup",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            self.assertEqual(merged.returncode, 0, merged.stderr)
            _, manifest = load_structured_document(manifest_path)
            self.assertEqual(manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["text"], "")
            self.assertEqual(
                manifest["scenes"][0]["cuts"][1]["audio"]["narration"]["text"],
                "ひびの向こうで、約束が目を覚まします。",
            )
            self.assertEqual(manifest["scenes"][0]["cuts"][2]["audio"]["narration"]["text"], "")

            manifest["audio_story_plan"] = {
                "schema_version": "audio_story_plan_v1",
                "authoring_provenance": "audio_story_director",
                "authoring_status": "authored",
                "audience_promise": "約束が目を覚ました理由を追う",
                "narrator_bible": {
                    "relationship_to_story": "limited_observer",
                    "knowledge_boundary": ["主人公が知ったことだけを語る"],
                    "emotional_permission": ["驚きに寄り添う"],
                    "forbidden_attitudes": ["答えを先に断定する"],
                },
                "open_loops": [],
                "scene_arcs": [
                    {
                        "scene_id": 10,
                        "attention_state": "release",
                        "audience_state_before": "ひびの意味を知らない",
                        "audience_state_after": "約束の兆しだと分かる",
                        "semantic_load": "medium",
                    }
                ],
                "silence_budget": {"protected_moments": []},
                "continuous_full_draft": "ひびの向こうで、約束が目を覚まします。",
            }
            manifest["narration_spans"] = [
                {
                    "span_id": "ns_001",
                    "source_cut_ids": ["scene10_cut1.1"],
                    "story_job": "payoff",
                    "opened_loop_ids": [],
                    "closed_loop_ids": [],
                    "text": "ひびの向こうで、約束が目を覚まします。",
                    "tts_text": "ひびの むこうで、やくそくが めを さまします。",
                    "audio_visual_relation": "causal_alignment",
                    "tts_generation_group_id": "full_run_01",
                }
            ]
            self.assertEqual(validate_audio_story_contract(manifest), [])

    def test_prepare_materializes_full_run_audio_story_scratch_and_prompt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_audio_story_prepare_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    scene_summary: "約束を思い出す"
    cuts:
      - cut_id: 1
        visual_beat: "古い印を見つめる"
        audio:
          narration:
            authoring_status: human_locked
            text: "この約束だけは、忘れられません。"
            tts_text: "この やくそくだけは、わすれられません。"
      - cut_id: 2
        visual_beat: "約束の相手へ振り返る"
  - scene_id: 20
    scene_summary: "帰る道を選ぶ"
    cuts:
      - cut_id: 1
        visual_beat: "出口へ踏み出す"
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--scene-ids",
                    "10",
                    "--min-cuts",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            full_run_path = run_dir / "scratch" / "narration" / "audio_story.yaml"
            self.assertTrue(full_run_path.is_file())
            import yaml

            full_run = yaml.safe_load(full_run_path.read_text(encoding="utf-8"))
            self.assertEqual(full_run["schema_version"], "narration_audio_story_scratch_v1")
            self.assertEqual(
                [arc["scene_id"] for arc in full_run["audio_story_plan"]["scene_arcs"]],
                [10, 20],
            )
            self.assertEqual(full_run["audio_story_plan"]["authoring_status"], "draft")
            self.assertEqual(full_run["audio_story_plan"]["continuous_full_draft"], "")
            self.assertEqual(full_run["narration_spans"], [])
            self.assertEqual(
                full_run["locked_cut_inputs"],
                [
                    {
                        "selector": "scene10_cut1",
                        "authoring_status": "human_locked",
                        "text": "この約束だけは、忘れられません。",
                        "tts_text": "この やくそくだけは、わすれられません。",
                        "read_only": True,
                    }
                ],
            )

            scene10 = yaml.safe_load(
                (run_dir / "scratch" / "narration" / "scene10.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual([cut["cut_id"] for cut in scene10["cuts"]], [1, 2])
            self.assertFalse((run_dir / "scratch" / "narration" / "scene20.yaml").exists())
            self.assertTrue(scene10["cuts"][0]["read_only"])
            self.assertTrue(scene10["cuts"][0]["locked"])
            self.assertEqual(scene10["cuts"][0]["authoring_status"], "human_locked")
            self.assertEqual(scene10["cuts"][0]["narration_text"], "この約束だけは、忘れられません。")

            prompt = (run_dir / "scratch" / "narration" / "authoring_prompt.md").read_text(encoding="utf-8")
            self.assertIn("audio_story_plan", prompt)
            self.assertIn("continuous_full_draft", prompt)
            self.assertIn("narration_spans", prompt)
            self.assertIn("scene10_cut1", prompt)
            self.assertIn("scene20_cut1", prompt)
            self.assertIn("この約束だけは、忘れられません。", prompt)

            full_run["audio_story_plan"]["audience_promise"] = "既存の全編設計は保持する"
            full_run_path.write_text(
                yaml.safe_dump(full_run, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            manifest_path.write_text(
                manifest_path.read_text(encoding="utf-8").replace(
                    '        visual_beat: "約束の相手へ振り返る"',
                    '        visual_beat: "約束の相手へ振り返る"\n'
                    "        audio:\n"
                    "          narration:\n"
                    "            authoring_status: human_locked\n"
                    '            text: "彼は、帰ると決めました。"\n'
                    '            tts_text: "かれは、かえると きめました。"',
                ),
                encoding="utf-8",
            )
            rerun = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--scene-ids",
                    "10",
                    "--min-cuts",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            refreshed_story = yaml.safe_load(full_run_path.read_text(encoding="utf-8"))
            refreshed_scene10 = yaml.safe_load(
                (run_dir / "scratch" / "narration" / "scene10.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(refreshed_story["audio_story_plan"]["audience_promise"], "既存の全編設計は保持する")
            self.assertEqual(
                [item["selector"] for item in refreshed_story["locked_cut_inputs"]],
                ["scene10_cut1", "scene10_cut2"],
            )
            self.assertTrue(refreshed_scene10["cuts"][1]["read_only"])
            self.assertEqual(refreshed_scene10["cuts"][1]["narration_text"], "彼は、帰ると決めました。")

    def test_prepare_projects_design_keys_into_narration_authoring_prompt(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_projection_prepare_") as td:
            run_dir = Path(td)
            (run_dir / "video_manifest.md").write_text(
                """```yaml
video_metadata:
  time: "17世紀末フランス・ルイ14世時代"
scenes:
  - scene_id: 10
    time_of_day: "朝"
    scene_intent:
      withheld_information: ["舞踏会への招待"]
      handoff_notes:
        p700_narration: ["自由への願いを補う"]
    cuts:
      - cut_id: 1
        visual_beat: "灰の床で出口へ視線を向ける"
        cut_contract:
          narration_contract:
            story_role:
              voice_function: emotion
              must_cover: ["自由への願い"]
              must_not_reveal: ["妖精の登場"]
            visual_distance:
              distance_policy: contextual
              visible_facts_in_frame: ["灰の床", "出口を見る視線"]
              narration_should_add: ["抑圧されても願いは消えない"]
          motion_contract:
            motion_brief: "出口へ駆け出す"
```
""",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text(
                """```yaml
script_metadata:
  ending_mode: happy
scenes: []
```
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--min-cuts",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            prompt = (run_dir / "scratch" / "narration" / "authoring_prompt.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("narration_prompt_projection_registry_v1", prompt)
            self.assertIn("背景文脈（自動的に読み上げない）", prompt)
            self.assertIn("17世紀末フランス・ルイ14世時代", prompt)
            self.assertIn("happy", prompt)
            self.assertIn("条件付き候補（必要な場合だけ語る）", prompt)
            self.assertIn("朝", prompt)
            self.assertIn("優先して追加する価値", prompt)
            self.assertIn("抑圧されても願いは消えない", prompt)
            self.assertIn("画面の見たままなので原則言い直さない", prompt)
            self.assertIn("灰の床", prompt)
            self.assertIn("妖精の登場", prompt)
            self.assertIn("spoken_projection=must_not_surface", prompt)
            self.assertNotIn("出口へ駆け出す", prompt)
            self.assertEqual(prompt.count("17世紀末フランス・ルイ14世時代"), 1)
            self.assertEqual(prompt.count("このシーンの時間帯"), 1)

    def test_revision_aware_merge_updates_script_then_syncs_manifest(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_multiagent_revision_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"
            scratch_dir = run_dir / "scratch" / "narration"
            scratch_dir.mkdir(parents=True)
            (scratch_dir / "audio_story.yaml").write_text(
                """schema_version: narration_audio_story_scratch_v1
audio_story_plan:
  schema_version: audio_story_plan_v1
  authoring_provenance: audio_story_director
  authoring_status: authored
  audience_promise: "約束を守るために帰れるかを最後まで追う"
  narrator_bible:
    relationship_to_story: limited_observer
    knowledge_boundary: ["主人公が知ったことだけを語る"]
    emotional_permission: ["迷いに寄り添う"]
    forbidden_attitudes: ["結末を先に断定する"]
  open_loops: []
  scene_arcs:
    - scene_id: 10
      attention_state: release
      audience_state_before: "帰る理由を探している"
      audience_state_after: "約束が決断を生んだと分かる"
      semantic_load: medium
      incoming_causal_question: "なぜ帰るのか"
      outgoing_causal_pressure: "選んだ道を進む"
  silence_budget:
    intentional_silence_cut_ids: []
    principles: ["決断後に余白を置く"]
  continuous_full_draft: "彼が帰るのは、約束を思い出したからです。"
narration_spans:
  - span_id: ns_001
    source_cut_ids: [scene10_cut1]
    story_job: payoff
    opened_loop_ids: []
    closed_loop_ids: []
    text: "彼が帰るのは、約束を思い出したからです。"
    tts_text: "かれが かえるのは、やくそくを おもいだしたからです。"
    audio_visual_relation: causal_alignment
    prosody: {pace: release, pause_function: handoff}
    tts_generation_group_id: full_run_01
""",
                encoding="utf-8",
            )
            script_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        narration: ""
        tts_text: ""
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        image_generation:
          output: assets/scenes/scene10_cut1.png
        audio:
          narration:
            text: ""
            tts_text: ""
            tool: elevenlabs
            output: ""
```
""",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
            )
            _, before_manifest = load_structured_document(manifest_path)
            before_revision = before_manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["revision"]["number"]
            (scratch_dir / "scene10.yaml").write_text(
                """scene_id: 10
cuts:
  - cut_id: 1
    target_function: "causal_bridge"
    must_cover: ["帰る理由"]
    must_avoid: []
    done_when: ["理由が声で伝わる"]
    narration_text: "彼が帰るのは、約束を思い出したからです。"
    tts_text: "かれが かえるのは、やくそくを おもいだしたからです。"
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            _, script = load_structured_document(script_path)
            _, manifest = load_structured_document(manifest_path)
            script_cut = script["scenes"][0]["cuts"][0]
            narration = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(script_cut["narration"], "彼が帰るのは、約束を思い出したからです。")
            self.assertEqual(narration["text"], script_cut["narration"])
            self.assertGreater(narration["revision"]["number"], before_revision)
            self.assertEqual(narration["source_binding"]["script_selector"], "scene10_cut1")
            self.assertEqual(narration["output"], "")
            self.assertEqual(
                script["audio_story_plan"]["continuous_full_draft"],
                "彼が帰るのは、約束を思い出したからです。",
            )
            self.assertEqual(script["narration_spans"][0]["span_id"], "ns_001")
            self.assertEqual(manifest["narration_spans"][0]["source_cut_ids"], ["scene10_cut1"])
            self.assertEqual(validate_audio_story_contract(manifest), [])

            import yaml

            manifest.pop("audio_story_plan")
            manifest.pop("narration_spans")
            manifest_path.write_text(
                "```yaml\n" + yaml.safe_dump(manifest, sort_keys=False, allow_unicode=True) + "```\n",
                encoding="utf-8",
            )
            repaired = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            _, repaired_manifest = load_structured_document(manifest_path)
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            self.assertEqual(repaired_manifest["narration_spans"][0]["span_id"], "ns_001")
            self.assertEqual(
                repaired_manifest["audio_story_plan"]["continuous_full_draft"],
                "彼が帰るのは、約束を思い出したからです。",
            )

            audio_story_path = scratch_dir / "audio_story.yaml"
            audio_story_path.write_text(
                audio_story_path.read_text(encoding="utf-8").replace(
                    '    text: "彼が帰るのは、約束を思い出したからです。"',
                    '    text: "source cutと一致しない原稿です。"',
                ),
                encoding="utf-8",
            )
            script_before_drifted_merge = script_path.read_text(encoding="utf-8")
            drifted = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("audio_story.yaml is inconsistent with cut narration", drifted.stderr)
            self.assertEqual(script_path.read_text(encoding="utf-8"), script_before_drifted_merge)

    def test_revision_aware_merge_derives_canonical_global_contract_when_scratch_is_absent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_global_fallback_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"
            scratch_dir = run_dir / "scratch" / "narration"
            scratch_dir.mkdir(parents=True)
            script_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    scene_summary: "問いを受け取る"
    cuts:
      - cut_id: 1
        narration: ""
        tts_text: ""
      - cut_id: 2
        narration: ""
        tts_text: ""
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        image_generation: {output: assets/scenes/scene10_cut1.png}
        audio: {narration: {text: "", tts_text: "", tool: elevenlabs, output: ""}}
      - cut_id: 2
        image_generation: {output: assets/scenes/scene10_cut2.png}
        audio: {narration: {text: "", tts_text: "", tool: elevenlabs, output: ""}}
```
""",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            (scratch_dir / "scene10.yaml").write_text(
                """scene_id: 10
cuts:
  - cut_id: 1
    target_function: first_question
    must_cover: ["問い"]
    must_avoid: []
    done_when: ["問いが残る"]
    narration_text: "扉の向こうで、何が待っているのでしょう。"
    tts_text: "とびらの むこうで、なにが まっているのでしょう。"
  - cut_id: 2
    target_function: aftertaste
    must_cover: ["選択"]
    must_avoid: []
    done_when: ["選択が伝わる"]
    narration_text: "それでも彼は、自分の足で進む道を選びました。"
    tts_text: "それでも かれは、じぶんの あしで すすむ みちを えらびました。"
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            _, script = load_structured_document(script_path)
            _, manifest = load_structured_document(manifest_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                script["audio_story_plan"]["continuous_full_draft"],
                "扉の向こうで、何が待っているのでしょう。\nそれでも彼は、自分の足で進む道を選びました。",
            )
            self.assertEqual(
                [span["source_cut_ids"] for span in script["narration_spans"]],
                [["scene10_cut1"], ["scene10_cut2"]],
            )
            self.assertEqual(
                [span["tts_generation_group_id"] for span in script["narration_spans"]],
                ["full_run_01", "full_run_01"],
            )
            import yaml

            derived_scratch = yaml.safe_load(
                (scratch_dir / "audio_story.yaml").read_text(encoding="utf-8")
            )
            self.assertEqual(
                derived_scratch["audio_story_plan"]["continuous_full_draft"],
                script["audio_story_plan"]["continuous_full_draft"],
            )
            self.assertEqual(
                derived_scratch["audio_story_plan"]["authoring_provenance"],
                "derived_legacy_cut_projection",
            )
            self.assertEqual(derived_scratch["audio_story_plan"]["authoring_status"], "changes_requested")
            self.assertIn(
                "audio_story_plan requires Audio Story Director review before p720 can pass",
                validate_audio_story_contract(manifest),
            )

            derived_scratch["audio_story_plan"]["authoring_status"] = "authored"
            (scratch_dir / "audio_story.yaml").write_text(
                yaml.safe_dump(derived_scratch, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            unreviewed_provenance = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            self.assertNotEqual(unreviewed_provenance.returncode, 0)
            self.assertIn("authoring_provenance(audio_story_director)", unreviewed_provenance.stderr)

            derived_scratch["audio_story_plan"]["authoring_provenance"] = "audio_story_director"
            derived_scratch["narration_spans"] = list(reversed(derived_scratch["narration_spans"]))
            derived_scratch["audio_story_plan"]["continuous_full_draft"] = "\n".join(
                span["text"] for span in derived_scratch["narration_spans"]
            )
            (scratch_dir / "audio_story.yaml").write_text(
                yaml.safe_dump(derived_scratch, sort_keys=False, allow_unicode=True),
                encoding="utf-8",
            )
            script_before_reordered_merge = script_path.read_text(encoding="utf-8")
            reordered = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            self.assertNotEqual(reordered.returncode, 0)
            self.assertIn("must follow canonical script cut order", reordered.stderr)
            self.assertEqual(script_path.read_text(encoding="utf-8"), script_before_reordered_merge)

    def test_merge_preserves_frontend_locked_cut_and_uses_it_for_global_spans(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_locked_merge_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"
            scratch_dir = run_dir / "scratch" / "narration"
            scratch_dir.mkdir(parents=True)
            script_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        narration: "人が確定した約束です。"
        tts_text: "ひとが かくていした やくそくです。"
        narration_authoring:
          schema_version: narration_authoring_v1
          status: human_locked
          source: frontend
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        image_generation: {output: assets/scenes/scene10_cut1.png}
        audio:
          narration:
            text: "人が確定した約束です。"
            tts_text: "ひとが かくていした やくそくです。"
            tool: elevenlabs
            authoring_status: human_locked
            output: ""
            revision: {schema_version: narration_revision_v1}
```
""",
                encoding="utf-8",
            )
            (scratch_dir / "audio_story.yaml").write_text(
                """schema_version: narration_audio_story_scratch_v1
audio_story_plan:
  schema_version: audio_story_plan_v1
  authoring_provenance: audio_story_director
  authoring_status: authored
  audience_promise: "確定した約束の意味を最後まで追う"
  narrator_bible:
    relationship_to_story: limited_observer
    knowledge_boundary: ["確定済みの情報だけを語る"]
    emotional_permission: ["約束の重さに寄り添う"]
    forbidden_attitudes: ["確定文の改稿"]
  open_loops: []
  scene_arcs:
    - {scene_id: 10, attention_state: release, audience_state_before: "約束を知らない", audience_state_after: "約束を受け取る", semantic_load: medium}
  continuous_full_draft: "人が確定した約束です。"
narration_spans:
  - span_id: ns_001
    source_cut_ids: [scene10_cut1]
    story_job: payoff
    opened_loop_ids: []
    closed_loop_ids: []
    text: "人が確定した約束です。"
    tts_text: "ひとが かくていした やくそくです。"
    audio_visual_relation: causal_alignment
    tts_generation_group_id: full_run_01
""",
                encoding="utf-8",
            )
            (scratch_dir / "scene10.yaml").write_text(
                """scene_id: 10
cuts:
  - cut_id: 1
    narration_text: "agentが上書きしようとした文です。"
    tts_text: "えーじぇんとが うわがきしようとした ぶんです。"
""",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            _, script = load_structured_document(script_path)
            _, manifest = load_structured_document(manifest_path)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(script["scenes"][0]["cuts"][0]["narration"], "人が確定した約束です。")
            self.assertEqual(manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["text"], "人が確定した約束です。")
            self.assertEqual(script["narration_spans"][0]["text"], "人が確定した約束です。")

    def test_merge_holds_run_artifact_lock_before_reading_scratch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_merge_lock_") as td:
            run_dir = Path(td)
            script_path = run_dir / "script.md"
            manifest_path = run_dir / "video_manifest.md"
            scratch_dir = run_dir / "scratch" / "narration"
            scratch_dir.mkdir(parents=True)
            script_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        narration: ""
        tts_text: ""
```
""",
                encoding="utf-8",
            )
            manifest_path.write_text(
                """```yaml
scenes:
  - scene_id: 10
    cuts:
      - cut_id: 1
        image_generation: {output: assets/scenes/scene10_cut1.png}
        audio: {narration: {text: "", tts_text: "", tool: elevenlabs, output: ""}}
```
""",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "sync-narration-from-script.py"),
                    "--script",
                    str(script_path),
                    "--manifest",
                    str(manifest_path),
                ],
                check=True,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
            scratch_path = scratch_dir / "scene10.yaml"
            scratch_path.write_text(
                """scene_id: 10
cuts:
  - cut_id: 1
    target_function: payoff
    must_cover: ["選択"]
    must_avoid: []
    done_when: ["選択が伝わる"]
    narration_text: "古い原稿です。"
    tts_text: "ふるい げんこうです。"
""",
                encoding="utf-8",
            )

            lock_path = run_dir / ".locks" / "run_artifacts.lock"
            with sync_file_lock(lock_path):
                process = subprocess.Popen(
                    [
                        sys.executable,
                        str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                        "--run-dir",
                        str(run_dir),
                        "--force",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=REPO_ROOT,
                )
                time.sleep(0.15)
                self.assertIsNone(process.poll(), "merge must wait before reading any run artifact")
                scratch_path.write_text(
                    scratch_path.read_text(encoding="utf-8")
                    .replace("古い原稿です。", "ロック解放後の原稿です。")
                    .replace("ふるい げんこうです。", "ろっく かいほうごの げんこうです。"),
                    encoding="utf-8",
                )
            stdout, stderr = process.communicate(timeout=10)
            _, script = load_structured_document(script_path)

            self.assertEqual(process.returncode, 0, stdout + stderr)
            self.assertEqual(script["scenes"][0]["cuts"][0]["narration"], "ロック解放後の原稿です。")

    def test_prepare_and_merge_preserves_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_multiagent_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 10",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        audio:",
                        "          narration:",
                        "            text: \"\"",
                        "            tts_text: \"\"",
                        "            tool: \"elevenlabs\"",
                        "            output: \"assets/audio/scene10_cut01.mp3\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--scene-ids",
                    "10",
                    "--min-cuts",
                    "1",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            scratch = run_dir / "scratch" / "narration" / "scene10.yaml"
            text = scratch.read_text(encoding="utf-8")
            self.assertIn("target_function", text)
            self.assertIn("must_cover", text)

            scratch.write_text(
                "\n".join(
                    [
                        "scene_id: 10",
                        "cuts:",
                        "  - cut_id: 1",
                        "    target_function: \"inner_state\"",
                        "    must_cover: [\"迷い\"]",
                        "    must_avoid: [\"カメラ\"]",
                        "    done_when: [\"内面情報を1つ足す\"]",
                        "    narration_text: \"彼は、まだ一歩を決めきれずにいます。\"",
                        "    tts_text: \"かれは、まだ いっぽを きめきれずにいます。\"",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            _, manifest = load_structured_document(manifest_path)
            contract = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["contract"]
            self.assertEqual(contract["target_function"], "inner_state")
            self.assertEqual(contract["must_cover"], ["迷い"])
            self.assertEqual(contract["must_avoid"], ["カメラ"])
            self.assertEqual(manifest["scenes"][0]["cuts"][0]["audio"]["narration"]["tts_text"], "かれは、まだ いっぽを きめきれずにいます。")

    def test_merge_materializes_tts_text_from_structured_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="toc_narration_multiagent_v3_") as td:
            run_dir = Path(td)
            manifest_path = run_dir / "video_manifest.md"
            manifest_path.write_text(
                "\n".join(
                    [
                        "```yaml",
                        "scenes:",
                        "  - scene_id: 10",
                        "    cuts:",
                        "      - cut_id: 1",
                        "        audio:",
                        "          narration:",
                        "            text: \"\"",
                        "            tts_text: \"\"",
                        "            tool: \"elevenlabs\"",
                        "            output: \"assets/audio/scene10_cut01.mp3\"",
                        "```",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "toc-immersive-narration-multiagent.py"),
                    "--run-dir",
                    str(run_dir),
                    "--scene-ids",
                    "10",
                    "--min-cuts",
                    "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            scratch = run_dir / "scratch" / "narration" / "scene10.yaml"
            scratch.write_text(
                "\n".join(
                    [
                        "scene_id: 10",
                        "cuts:",
                        "  - cut_id: 1",
                        "    target_function: \"inner_state\"",
                        "    must_cover: [\"よろこび\"]",
                        "    must_avoid: []",
                        "    done_when: [\"声の勢いが伝わる\"]",
                        "    spoken_context: \"かのじょは こえを はずませながら いいました。\"",
                        "    voice_tags: [\"excited\", \"laughs harder\"]",
                        "    spoken_body: \"ほんとうに ありがとう！\"",
                        "    stability_profile: \"creative\"",
                        "    narration_text: \"彼女は声を弾ませて礼を言います。\"",
                        "    tts_text: \"\"",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(REPO_ROOT / "scripts" / "ai" / "merge-immersive-narration.py"),
                    "--run-dir",
                    str(run_dir),
                    "--force",
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            _, manifest = load_structured_document(manifest_path)
            narration = manifest["scenes"][0]["cuts"][0]["audio"]["narration"]
            self.assertEqual(
                narration["tts_text"],
                "かのじょは こえを はずませながら いいました。 [excited][laughs harder] ほんとうに ありがとう！",
            )
