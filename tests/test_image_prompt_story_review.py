import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toc.harness import load_structured_document


def _load_review_module(repo_root: Path):
    script = repo_root / "scripts" / "review-image-prompt-story-consistency.py"
    spec = importlib.util.spec_from_file_location("review_image_prompt_story_consistency", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


def _load_export_module(repo_root: Path):
    script = repo_root / "scripts" / "export-image-prompt-collection.py"
    spec = importlib.util.spec_from_file_location("export_image_prompt_collection", script)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)  # type: ignore[assignment]
    return mod


def _structured_prompt(scene_lines: str) -> str:
    return f"""[全体 / 不変条件]
実写映画調、画像内テキストなし。

[登場人物]
浦島太郎。

[小道具 / 舞台装置]
海亀、浜辺。

[シーン]
{scene_lines}

[連続性]
前後カットと衣装・天候・位置関係を維持する。

[禁止]
ロゴ、字幕、ウォーターマーク。
"""


class TestImagePromptStoryReview(unittest.TestCase):
    def test_review_flags_missing_required_prompt_blocks_on_unstructured_prompt(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_review_module(repo_root)

        prompt_collection = """# Image Prompt Collection

件数: `1`

## scene03_cut01

- output: `assets/scenes/scene03_cut01.png`
- narration: `太郎がその中へ入ると、海の音がすっと遠くなります。`
- rationale: `anchor`

```text
実写、シネマティック。海中トンネルを進む。
```
"""
        manifest = {
            "assets": {
                "character_bible": [
                    {"character_id": "urashima", "review_aliases": ["太郎", "浦島太郎"]},
                ]
            },
            "scenes": [
                {
                    "scene_id": 3,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {
                                "character_ids": ["urashima"],
                                "object_ids": [],
                            },
                            "audio": {"narration": {"text": "太郎がその中へ入ると、海の音がすっと遠くなります。"}},
                        }
                    ],
                }
            ],
        }
        entries = mod.parse_prompt_collection(prompt_collection)
        results = mod.review_entries(
            entries,
            manifest=manifest,
            story_scene_map={3: "海中トンネル"},
            script_scene_map={},
            story_text="",
            script_text="",
        )
        findings = [finding.message for outcome in results for finding in outcome.findings if finding.code == "missing_required_prompt_block"]
        self.assertIn("prompt is missing required block `[全体 / 不変条件]`.", findings)
        self.assertIn("prompt is missing required block `[禁止]`.", findings)

    def test_review_flags_missing_source_anchor_and_missing_object_id(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_review_module(repo_root)

        prompt_collection = """# Image Prompt Collection

件数: `1`

## scene02_cut01

- output: `assets/scenes/scene02_cut01.png`
- narration: `浦島太郎が亀にまたがって沖へ進む。`
- rationale: `anchor`

```text
[シーン]
浦島太郎が海へ向かう浜辺。波しぶき。
```
"""
        manifest = {
            "assets": {
                "object_bible": [
                    {
                        "object_id": "adult_turtle",
                        "review_aliases": ["亀"],
                    }
                ]
            },
            "scenes": [
                {
                    "scene_id": 2,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {
                                "character_ids": ["urashima"],
                                "object_ids": [],
                            },
                            "audio": {"narration": {"text": "浦島太郎が亀にまたがって沖へ進む。"}},
                        }
                    ],
                }
            ],
        }
        entries = mod.parse_prompt_collection(prompt_collection)
        results = mod.review_entries(
            entries,
            manifest=manifest,
            story_scene_map={2: "浦島太郎が亀にまたがる場面"},
            script_scene_map={},
            story_text="浦島太郎が亀にまたがる。",
            script_text="",
        )
        findings = [finding.code for outcome in results for finding in outcome.findings]
        self.assertIn("source_anchor_missing_from_prompt", findings)
        self.assertIn("missing_object_id", findings)

    def test_review_flags_prompt_character_when_character_ids_empty(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_review_module(repo_root)

        prompt_collection = """# Image Prompt Collection

件数: `1`

## scene05_cut02

- output: `assets/scenes/scene05_cut02.png`
- narration: `乙姫が浦島太郎を迎える。`
- rationale: `anchor`

```text
[全体 / 不変条件]
実写映画調、画像内テキストなし。

[登場人物]
乙姫が浦島太郎を見つめ、浦島太郎が乙姫へ向き直る。

[小道具 / 舞台装置]
竜宮城の広間。

[シーン]
乙姫が浦島太郎を迎える瞬間。

[連続性]
衣装と空間の一貫性を保つ。

[禁止]
ロゴ、字幕、ウォーターマーク。
```
"""
        manifest = {
            "assets": {
                "character_bible": [
                    {"character_id": "urashima", "review_aliases": ["浦島太郎", "太郎"]},
                    {"character_id": "otohime", "review_aliases": ["乙姫"]},
                ]
            },
            "scenes": [
                {
                    "scene_id": 5,
                    "cuts": [
                        {
                            "cut_id": 2,
                            "image_generation": {
                                "character_ids": [],
                                "object_ids": [],
                            },
                            "audio": {"narration": {"text": "乙姫が浦島太郎を迎える。"}},
                        }
                    ],
                }
            ],
        }
        entries = mod.parse_prompt_collection(prompt_collection)
        results = mod.review_entries(
            entries,
            manifest=manifest,
            story_scene_map={5: "乙姫が浦島太郎を迎える"},
            script_scene_map={},
            story_text="",
            script_text="",
        )
        findings = [finding.code for outcome in results for finding in outcome.findings]
        self.assertIn("prompt_mentions_character_but_character_ids_empty", findings)

    def test_review_does_not_flag_shorter_source_term_when_longer_prompt_term_contains_it(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_review_module(repo_root)

        prompt_collection = """# Image Prompt Collection

件数: `1`

## scene03_cut01

- output: `assets/scenes/scene03_cut01.png`
- narration: `太郎がその中へ入ると、海の音がすっと遠くなります。`
- rationale: `anchor`

```text
[全体 / 不変条件]
実写、シネマティック。

[登場人物]
浦島太郎が海亀に乗って進む。

[小道具 / 舞台装置]
海亀、アクリルトンネル。

[シーン]
浦島太郎が海中トンネルへ入る。

[連続性]
前の海辺から連続する。

[禁止]
文字なし。
```
"""
        manifest = {
            "assets": {
                "character_bible": [
                    {"character_id": "urashima", "review_aliases": ["太郎", "浦島太郎"]},
                ]
            },
            "scenes": [
                {
                    "scene_id": 3,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {
                                "character_ids": ["urashima"],
                                "object_ids": [],
                            },
                            "audio": {"narration": {"text": "太郎がその中へ入ると、海の音がすっと遠くなります。"}},
                        }
                    ],
                }
            ],
        }
        entries = mod.parse_prompt_collection(prompt_collection)
        results = mod.review_entries(
            entries,
            manifest=manifest,
            story_scene_map={},
            script_scene_map={},
            story_text="",
            script_text="",
        )
        findings = [finding.code for outcome in results for finding in outcome.findings]
        self.assertNotIn("source_anchor_missing_from_prompt", findings)

    def test_review_flags_non_self_contained_prompt_and_english_term(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_review_module(repo_root)

        prompt_collection = """# Image Prompt Collection

件数: `1`

## scene04_cut01

- output: `assets/scenes/scene04_cut01.png`
- narration: `竜宮城の門が開く。`
- rationale: `anchor`

```text
[全体 / 不変条件]
実写、シネマティック。

[登場人物]
乙姫と浦島太郎。

[小道具 / 舞台装置]
竜宮門。

[シーン]
scene03_cut03 の次として、rideable な海亀の到着後に門が開く。

[連続性]
前カットと一致させる。

[禁止]
文字なし。
```
"""
        manifest = {
            "assets": {"character_bible": [{"character_id": "urashima", "review_aliases": ["太郎", "浦島太郎"]}]},
            "scenes": [
                {
                    "scene_id": 4,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {"character_ids": ["urashima"], "object_ids": []},
                            "audio": {"narration": {"text": "竜宮城の門が開く。"}},
                        }
                    ],
                }
            ],
        }
        entries = mod.parse_prompt_collection(prompt_collection)
        results = mod.review_entries(
            entries,
            manifest=manifest,
            story_scene_map={},
            script_scene_map={},
            story_text="",
            script_text="",
        )
        findings = [finding.code for outcome in results for finding in outcome.findings]
        self.assertIn("prompt_not_self_contained", findings)
        self.assertIn("non_japanese_prompt_term", findings)

    def test_review_flags_prompt_only_local_mismatch(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_review_module(repo_root)

        prompt_collection = """# Image Prompt Collection

件数: `1`

## scene05_cut02

- output: `assets/scenes/scene05_cut02.png`
- narration: `乙姫が玉座の前に立つ。`
- rationale: `anchor`

```text
[シーン]
乙姫の背後で亀がこちらを見る。
```
"""
        manifest = {
            "assets": {
                "character_bible": [
                    {"character_id": "otohime", "review_aliases": ["乙姫"]},
                ],
                "object_bible": [
                    {"object_id": "adult_turtle", "review_aliases": ["亀"]},
                ],
            },
            "scenes": [
                {
                    "scene_id": 5,
                    "cuts": [
                        {
                            "cut_id": 2,
                            "image_generation": {
                                "character_ids": ["otohime"],
                                "object_ids": [],
                            },
                            "audio": {"narration": {"text": "乙姫が玉座の前に立つ。"}},
                        }
                    ],
                }
            ],
        }

        entries = mod.parse_prompt_collection(prompt_collection)
        results = mod.review_entries(
            entries,
            manifest=manifest,
            story_scene_map={5: "乙姫が玉座の前に立つ"},
            script_scene_map={},
            story_text="乙姫が玉座の前に立つ。",
            script_text="",
        )
        findings = [finding.code for outcome in results for finding in outcome.findings]
        self.assertIn("prompt_only_local_mismatch", findings)

    def test_review_flags_missing_required_prompt_blocks(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_review_module(repo_root)

        prompt_collection = """# Image Prompt Collection

件数: `1`

## scene01_cut01

- output: `assets/scenes/scene01_cut01.png`
- narration: `浦島太郎が浜辺に立つ。`
- rationale: `anchor`

```text
[シーン]
浦島太郎が浜辺に立つ。
```
"""
        manifest = {
            "assets": {
                "character_bible": [{"character_id": "urashima", "review_aliases": ["浦島太郎"]}],
            },
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {"character_ids": ["urashima"], "object_ids": []},
                            "audio": {"narration": {"text": "浦島太郎が浜辺に立つ。"}},
                        }
                    ],
                }
            ],
        }
        results = mod.review_entries(
            mod.parse_prompt_collection(prompt_collection),
            manifest=manifest,
            story_scene_map={1: "浦島太郎が浜辺に立つ。"},
            script_scene_map={},
            story_text="浦島太郎が浜辺に立つ。",
            script_text="",
        )
        block_messages = [finding.message for outcome in results for finding in outcome.findings if finding.code == "missing_required_prompt_block"]
        self.assertIn("prompt is missing required block `[全体 / 不変条件]`.", block_messages)
        self.assertIn("prompt is missing required block `[登場人物]`.", block_messages)
        self.assertIn("prompt is missing required block `[連続性]`.", block_messages)

    def test_required_prompt_block_detection_accepts_fully_structured_prompt(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        mod = _load_review_module(repo_root)

        prompt_collection = f"""# Image Prompt Collection

件数: `1`

## scene01_cut01

- output: `assets/scenes/scene01_cut01.png`
- narration: `浦島太郎が浜辺に立つ。`
- rationale: `anchor`

```text
{_structured_prompt("浦島太郎が浜辺に立つ。")}
```
"""
        manifest = {
            "assets": {
                "character_bible": [{"character_id": "urashima", "review_aliases": ["浦島太郎"]}],
                "object_bible": [{"object_id": "beach", "review_aliases": ["浜辺"]}],
            },
            "scenes": [
                {
                    "scene_id": 1,
                    "cuts": [
                        {
                            "cut_id": 1,
                            "image_generation": {"character_ids": ["urashima"], "object_ids": ["beach"]},
                            "audio": {"narration": {"text": "浦島太郎が浜辺に立つ。"}},
                        }
                    ],
                }
            ],
        }
        results = mod.review_entries(
            mod.parse_prompt_collection(prompt_collection),
            manifest=manifest,
            story_scene_map={1: "浦島太郎が浜辺に立つ。"},
            script_scene_map={},
            story_text="浦島太郎が浜辺に立つ。",
            script_text="",
        )
        findings = [finding.code for outcome in results for finding in outcome.findings]
        self.assertNotIn("missing_required_prompt_block", findings)

    def test_export_preserves_reason_keys_and_messages(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        export_mod = _load_export_module(repo_root)

        with tempfile.TemporaryDirectory(prefix="toc_prompt_export_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)
            prompt_collection = run_dir / "image_prompt_collection.md"
            prompt_collection.write_text(
                """# Image Prompt Collection

件数: `1`

## scene01_cut01

- output: `assets/scenes/scene01_cut01.png`
- narration: `浦島太郎が浜辺に立つ。`
- rationale: `anchor`
- agent_review_ok: `false`
- human_review_ok: `false`
- agent_review_reason_keys: `source_anchor_missing_from_prompt, missing_object_id`
- agent_review_reason_messages:
  - `source context mentions '浦島太郎' but the prompt does not.`
  - `source context implies object 'adult_turtle' but object_ids does not include it.`

```text
[シーン]
浜辺の波。
```
""",
                encoding="utf-8",
            )

            manifest = {
                "scenes": [
                    {
                        "scene_id": 1,
                        "cuts": [
                            {
                                "cut_id": 1,
                                "still_image_plan": {"mode": "generate_still", "rationale": "anchor"},
                                "image_generation": {
                                    "output": "assets/scenes/scene01_cut01.png",
                                    "prompt": "[シーン]\n浜辺の波。",
                                },
                                "audio": {"narration": {"text": "浦島太郎が浜辺に立つ。"}},
                            }
                        ],
                    }
                ]
            }
            rendered = export_mod.render_collection(
                manifest,
                mode_filter="generate_still",
                existing_states=export_mod.load_existing_review_states(prompt_collection),
            )
            self.assertIn("- agent_review_reason_keys: `source_anchor_missing_from_prompt, missing_object_id`", rendered)
            self.assertIn("  - `source context mentions '浦島太郎' but the prompt does not.`", rendered)
            self.assertIn("  - `source context implies object 'adult_turtle' but object_ids does not include it.`", rendered)

    def test_cli_writes_review_report(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="toc_prompt_review_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "image_prompt_collection.md").write_text(
                f"""# Image Prompt Collection

件数: `1`

## scene01_cut01

- output: `assets/scenes/scene01_cut01.png`
- narration: `浦島太郎が浜辺に立つ。`
- rationale: `anchor`

```text
{_structured_prompt("浦島太郎が浜辺に立つ。")}
```
""",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                """```yaml
assets:
  character_bible:
    - character_id: "urashima"
      review_aliases: ["浦島太郎"]
scenes:
  - scene_id: 1
    cuts:
      - cut_id: 1
        image_generation:
          character_ids: ["urashima"]
          object_ids: []
        audio:
          narration:
            text: "浦島太郎が浜辺に立つ。"
```""",
                encoding="utf-8",
            )
            (run_dir / "story.md").write_text(
                """```yaml
script:
  scenes:
    - scene_id: 1
      narration: "浦島太郎が浜辺に立つ。"
      visual: "浜辺"
```""",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text("# Script\n\n浦島太郎が浜辺に立つ。\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/review-image-prompt-story-consistency.py",
                    "--prompt-collection",
                    str(run_dir / "image_prompt_collection.md"),
                ],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            report = run_dir / "image_prompt_story_review.md"
            self.assertTrue(report.exists())
            text = report.read_text(encoding="utf-8")
            self.assertIn("# Image Prompt Story Review", text)
            self.assertIn("scene01_cut01", text)

    def test_review_can_autofix_missing_character_ids(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="toc_prompt_review_fix_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "image_prompt_collection.md").write_text(
                f"""# Image Prompt Collection

件数: `1`

## scene02_cut01

- output: `assets/scenes/scene02_cut01.png`
- narration: `浦島太郎が亀にまたがって沖へ進む。`
- rationale: `anchor`
- agent_review_ok: `true`
- human_review_ok: `false`

```text
{_structured_prompt("大人の海亀が波間を進む。")}
```
""",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                """```yaml
assets:
  character_bible:
    - character_id: "urashima"
      review_aliases: ["浦島太郎"]
    - character_id: "turtle"
      review_aliases: ["亀", "海亀"]
scenes:
  - scene_id: 2
    cuts:
      - cut_id: 1
        image_generation:
          character_ids: ["turtle"]
          object_ids: []
          prompt: |
            [全体 / 不変条件]
            実写映画調、画像内テキストなし。
            
            [登場人物]
            浦島太郎。
            
            [小道具 / 舞台装置]
            海亀、浜辺。
            
            [シーン]
            大人の海亀が波間を進む。
            
            [連続性]
            前後カットと衣装・天候・位置関係を維持する。
            
            [禁止]
            ロゴ、字幕、ウォーターマーク。
        audio:
          narration:
            text: "浦島太郎が亀にまたがって沖へ進む。"
```""",
                encoding="utf-8",
            )
            (run_dir / "story.md").write_text("# Story\n\n浦島太郎が亀にまたがる。\n", encoding="utf-8")
            (run_dir / "script.md").write_text("# Script\n\n浦島太郎が亀にまたがって沖へ進む。\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/review-image-prompt-story-consistency.py",
                    "--prompt-collection",
                    str(run_dir / "image_prompt_collection.md"),
                    "--fix-character-ids",
                ],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            _, manifest_data = load_structured_document(run_dir / "video_manifest.md")
            character_ids = manifest_data["scenes"][0]["cuts"][0]["image_generation"]["character_ids"]
            self.assertEqual(character_ids, ["turtle", "urashima"])
            report = (run_dir / "image_prompt_story_review.md").read_text(encoding="utf-8")
            self.assertIn("fixed_character_ids: `1`", report)
            collection = (run_dir / "image_prompt_collection.md").read_text(encoding="utf-8")
            self.assertIn("- agent_review_ok: `false`", collection)
            self.assertIn("- agent_review_reason_keys: `source_anchor_missing_from_prompt, missing_character_id`", collection)
            self.assertIn("  - `source context mentions '浦島太郎' but the prompt does not.`", collection)

    def test_rereview_clears_agent_reasons_after_prompt_fix(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="toc_prompt_review_rereview_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            prompt_collection = run_dir / "image_prompt_collection.md"
            prompt_collection.write_text(
                f"""# Image Prompt Collection

件数: `1`

## scene02_cut01

- output: `assets/scenes/scene02_cut01.png`
- narration: `浦島太郎が亀にまたがって沖へ進む。`
- rationale: `anchor`
- agent_review_ok: `false`
- human_review_ok: `false`
- agent_review_reason_keys: `source_anchor_missing_from_prompt, missing_character_id`
- agent_review_reason_messages:
  - `source context mentions '浦島太郎' but the prompt does not.`
  - `source context implies character 'urashima' via ['浦島太郎'], but character_ids does not include it.`

```text
{_structured_prompt("浦島太郎が亀にまたがって沖へ進む。")}
```
""",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                """```yaml
assets:
  character_bible:
    - character_id: "urashima"
      review_aliases: ["浦島太郎"]
    - character_id: "turtle"
      review_aliases: ["亀", "海亀"]
scenes:
  - scene_id: 2
    cuts:
      - cut_id: 1
        image_generation:
          character_ids: ["urashima", "turtle"]
          object_ids: []
        audio:
          narration:
            text: "浦島太郎が亀にまたがって沖へ進む。"
```""",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text("# Script\n\n浦島太郎が亀にまたがって沖へ進む。\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/review-image-prompt-story-consistency.py",
                    "--prompt-collection",
                    str(prompt_collection),
                    "--fail-on-findings",
                ],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            updated = prompt_collection.read_text(encoding="utf-8")
            self.assertIn("- agent_review_ok: `true`", updated)
            self.assertIn("- agent_review_reason_keys: ``", updated)
            self.assertIn("- agent_review_reason_messages:\n  - ``", updated)

    def test_review_allows_human_review_override(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="toc_prompt_review_bypass_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)

            (run_dir / "image_prompt_collection.md").write_text(
                f"""# Image Prompt Collection

件数: `1`

## scene02_cut01

- output: `assets/scenes/scene02_cut01.png`
- narration: `浦島太郎が亀にまたがって沖へ進む。`
- rationale: `anchor`
- agent_review_ok: `true`
- human_review_ok: `true`

```text
{_structured_prompt("大人の海亀が波間を進む。")}
```
""",
                encoding="utf-8",
            )
            (run_dir / "video_manifest.md").write_text(
                """```yaml
assets:
  character_bible:
    - character_id: "urashima"
      review_aliases: ["浦島太郎"]
    - character_id: "turtle"
      review_aliases: ["亀", "海亀"]
scenes:
  - scene_id: 2
    cuts:
      - cut_id: 1
        image_generation:
          character_ids: ["turtle"]
          object_ids: []
        audio:
          narration:
            text: "浦島太郎が亀にまたがって沖へ進む。"
```""",
                encoding="utf-8",
            )
            (run_dir / "script.md").write_text("# Script\n\n浦島太郎が亀にまたがって沖へ進む。\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/review-image-prompt-story-consistency.py",
                    "--prompt-collection",
                    str(run_dir / "image_prompt_collection.md"),
                    "--fail-on-findings",
                ],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            report = (run_dir / "image_prompt_story_review.md").read_text(encoding="utf-8")
            self.assertIn("- status: `WARN`", report)
            self.assertIn("- human_review_ok: `true`", report)
            collection = (run_dir / "image_prompt_collection.md").read_text(encoding="utf-8")
            self.assertIn("- agent_review_ok: `false`", collection)
            self.assertIn("- human_review_ok: `true`", collection)
            self.assertIn("- agent_review_reason_keys: `source_anchor_missing_from_prompt, missing_character_id`", collection)

    def test_set_human_review_updates_prompt_collection(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="toc_prompt_review_human_") as td:
            run_dir = Path(td) / "output" / "urashima_20990101_0000"
            run_dir.mkdir(parents=True, exist_ok=True)
            prompt_collection = run_dir / "image_prompt_collection.md"
            prompt_collection.write_text(
                f"""# Image Prompt Collection

件数: `1`

## scene02_cut01

- output: `assets/scenes/scene02_cut01.png`
- narration: `浦島太郎が亀にまたがって沖へ進む。`
- rationale: `anchor`
- agent_review_ok: `false`
- human_review_ok: `false`
- agent_review_reason_keys: `source_anchor_missing_from_prompt`
- agent_review_reason_messages:
  - `source context mentions '浦島太郎' but the prompt does not.`

```text
{_structured_prompt("大人の海亀が波間を進む。")}
```
""",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "scripts/review-image-prompt-story-consistency.py",
                    "--prompt-collection",
                    str(prompt_collection),
                    "--set-human-review",
                    "scene02_cut01",
                ],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            updated = prompt_collection.read_text(encoding="utf-8")
            self.assertIn("- human_review_ok: `true`", updated)
            self.assertIn("- agent_review_reason_keys: `source_anchor_missing_from_prompt`", updated)
