# Image Method: Reference Consistent Batch

## Use when
- sceneごとの静止画を一括生成し、被写体・視点・構図の一貫性を維持したいとき

## Scope
- この方式は **画像生成のみ** を担当する
- scene定義・動画生成は別カテゴリ方式で処理する

## Steps
1. 共通リファレンス（キャラ/手/バー/乗り物）を固定する
2. `video_manifest.md` から prompt collection を書き出し、anchor/reference が固定されているかをレビューする
3. `script.md` と突き合わせて、character_ids / ブロッキング / story intent の不整合と、必須 6 ブロック構造の欠落を review script で潰す
4. review script は各 cut に `agent_review_ok` と false 理由 key を書く
5. false reason に対応する修正を prompt collection / manifest に反映する
6. fix 後に再 review し、直った cut から `agent_review_ok: true` に戻す
7. `agent_review_ok=false` のまま進める cut だけ人間が `human_review_ok: true` と `human_review_reason` を付ける
8. scene定義（scene outline / asset brief）に沿って `sceneN.png` を一括生成する
9. 一貫性チェック（手・バー・視点・舞台連続性）を実施する

推奨コマンド:

```bash
python scripts/export-image-prompt-collection.py \
  --manifest output/<topic>_<timestamp>/video_manifest.md

python scripts/review-image-prompt-story-consistency.py \
  --prompt-collection output/<topic>_<timestamp>/image_prompt_collection.md \
  --fix-character-ids
```

Review rule:

- `agent_review_ok: false` の entry は reason key を必ず持つ
- 現行表記として `agent_review_reason_codes` を使っていてもよいが、意味は `agent_review_reason_keys` と同じに保つ
- `[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`, `[連続性]`, `[禁止]` のいずれかが欠けている prompt は `missing_required_prompt_block` として `agent_review_ok: false` にする
- prompt が他 cut や前の prompt を参照している場合は `prompt_not_self_contained` として `agent_review_ok: false` にする
- `rideable` のような英語 shorthand が本文に入っている場合は `non_japanese_prompt_term` として `agent_review_ok: false` にする
- prompt が人物を明示しているのに `image_generation.character_ids` が空なら `prompt_mentions_character_but_character_ids_empty` として `agent_review_ok: false` にする
- fix は prompt collection だけで終わらせず、必要なら source manifest に戻す
- fix 後に subagent が再 review し、解消した entry だけ `agent_review_ok: true` に戻す
- `human_review_ok: true` は finding を理解して例外許容した記録であり、subagent false reason を消すものではない
- story still は `still_image_plan.mode: generate_still` だけを既定対象にし、`reuse_anchor` / `no_dedicated_still` は明示的に `--image-plan-modes` を広げない限り生成しない

Canonical reason key:

- `missing_character_ids`
- `missing_object_ids`
- `environment_only_prompt`
- `missing_story_action`
- `missing_story_relationship`
- `continuity_anchor_missing`
- `reference_missing`
- `missing_required_prompt_block`
- `prompt_not_self_contained`
- `non_japanese_prompt_term`
- `prompt_mentions_character_but_character_ids_empty`
- `camera_or_composition_under_specified`

Required block review rule:

- `[全体 / 不変条件]`
- `[登場人物]`
- `[小道具 / 舞台装置]`
- `[シーン]`
- `[連続性]`
- `[禁止]`

上記 6 block のいずれかが欠けていれば、subagent はその entry を `agent_review_ok: false` にし、`missing_required_prompt_block` を reason key に含める。

## Prompt assembly (recommended)
image prompt は `scene_outline` の情報を「削らず」使う。未知トピックでの幻覚を避けるため、勝手に新情報を足さない。

補足:
- camera の記述は数値だけで終わらせず、`広め / 中広角 / 寄り` と `前景 / 中景 / 背景` を併記し、その shot で何を読ませるかを明示する。
- 生成前の正しい順番は、構造化 → anchor 決定 → reference 固定 → prompt 集レビュー → story consistency review → 生成。

Prompt の“型”（見出し/順序固定）は正本 `docs/implementation/image-prompting.md` を参照。
ここで重要なのは、**うまい一文を作ることではなく、構造化された prompt collection を anchor/reference 固定でレビューすること**。

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
