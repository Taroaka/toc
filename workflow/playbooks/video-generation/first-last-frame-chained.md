# Video Method: First Last Frame Chained

## Use when
- scene間遷移を滑らかにし、1本の連続映像として見せたいとき
- `sceneN.png` と `sceneN+1.png` を境界条件にして、clipを量産したいとき

## Scope
- この方式は **動画生成のみ** を担当する
- scene定義・画像生成は別カテゴリ方式で処理する

## Inputs (recommended)
- `scene_outline.global_constraints`
- `scene_outline.scenes[].continuity.anchor_to_next`
- `scene_outline.scenes[].continuity.must_match_prev/must_match_next`
- `scene_outline.scenes[].prompt_guidance.video_motion/video_negative`
- `assets/scenes/sceneN.png`（画像生成ステップの成果物）

## Steps
1. `sceneN.png -> sceneN+1.png` を first/last frame として clip生成する
2. prompt は `scene_outline` から組み立てる（global constraints + sceneN/sceneN+1 + continuity + video_motion）
3. 推奨: chaining frame（前clipの「ほぼ最終フレーム」）を保存した後、次clipの first frame として再materialize・再review・再approveして使う。provider実行中に未承認のframeへ動的差し替えしない
4. clipを結合し、継ぎ目（フェード/カット/急な画変化）を検査する

## Prompt assembly (recommended)
video prompt は「2つの静止画を自然に繋ぐための説明」に集中する。

1) Global（毎回入れる）
- `global_constraints.pov/style/must_include/must_avoid`

2) Bridge（clipごと）
- Scene N: `setting` / `characters_present` / `props_set_pieces` / `action_beats`
- Scene N+1: 同様（到達点として）
- `continuity.anchor_to_next` をそのまま使う（match-cut の意図）
- `prompt_guidance.video_motion`（動き）+ `video_negative`（禁止）
- `continuity.must_match_prev/must_match_next`（ブレると継ぎ目が出る要因）

3) Grounding
- 未知トピックでは `factual_anchors` を超える新規情報を足さない
- 追加の発明は `creative_inventions` を参照し「invented」として扱う

## If scene info is missing
- `scene_outline.scenes[].research_tasks` が `todo` の場合は生成を止め、先に evidence を埋める
  - evidence テンプレ: `workflow/scene-evidence-template.md`
  - Claude subagent（任意）: `.claude/agents/scene-evidence-researcher.md`

## Notes
- 未知トピック（現代人物/ニュース等）の場合は、promptに新規情報を勝手に足さない
  - `factual_anchors`（fact_id/source_id）を根拠として参照し、創作は `creative_inventions` として明示する
- clip内で中盤にフェード/暗転/別シーン化が起きる場合は、`video_negative` に以下を明記する
  - "no fade", "no cut", "no dissolve", "single continuous take"

## Output contract
- `assets/scenes/sceneN_to_sceneN+1.mp4`
- `assets/scenes/chaining/sceneN_end.png`（任意: chaining frame）
- 結合後 `video.mp4`（または中間clipリスト）
