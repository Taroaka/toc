# Image Method: Reference Consistent Batch

## Use when
- sceneごとの静止画を一括生成し、被写体・視点・構図の一貫性を維持したいとき

## Scope
- この方式は **画像生成のみ** を担当する
- scene定義・動画生成は別カテゴリ方式で処理する

## Steps
1. 共通リファレンス（キャラ/手/バー/乗り物）を固定する
2. `video_manifest.md` から prompt collection を書き出してレビューする
3. scene定義（scene outline / asset brief）に沿って `sceneN.png` を一括生成する
4. 一貫性チェック（手・バー・視点・舞台連続性）を実施する

推奨コマンド:

```bash
python scripts/export-image-prompt-collection.py \
  --manifest output/<topic>_<timestamp>/video_manifest.md
```

## Prompt assembly (recommended)
image prompt は `scene_outline` の情報を「削らず」使う。未知トピックでの幻覚を避けるため、勝手に新情報を足さない。

Prompt の“型”（見出し/順序固定）は正本 `docs/implementation/image-prompting.md` を参照。

1) Global（毎回入れる）
- `global_constraints.pov/style/must_include/must_avoid`
- `global_constraints.references.*`（ある場合）

2) Scene（sceneごと）
- `setting` / `characters_present` / `props_set_pieces` / `action_beats`
- `camera` / `lighting_color`
- `continuity.must_match_prev/must_match_next`（必要なら）
- `prompt_guidance.image_focus`（強調したい要素）
- `prompt_guidance.image_negative` + `global_constraints.must_avoid`（禁止）

3) Grounding（未知トピック用）
- `factual_anchors.fact_ids/source_ids` を参照し、創作は `creative_inventions` として明示する

## If scene info is missing
- `scene_outline.scenes[].research_tasks` が `todo` の場合は生成を止め、先に evidence を埋める
  - evidence テンプレ: `workflow/scene-evidence-template.md`
  - Claude subagent（任意）: `.claude/agents/scene-evidence-researcher.md`

## Output contract
- `assets/scenes/sceneN.png`（N=1..n）
- 画像品質チェック結果（欠損や不一致の記録）
- 推奨: 使った prompt/params を保存（例: `assets/prompts/image_sceneN.txt`）

Input expectations (recommended):
- `scene_outline.scenes[].setting`
- `scene_outline.scenes[].characters_present`
- `scene_outline.scenes[].props_set_pieces`
- `scene_outline.scenes[].camera` / `lighting_color`
- `scene_outline.scenes[].prompt_guidance.image_focus` / `image_negative`
