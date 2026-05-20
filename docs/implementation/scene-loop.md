# Scene-level Loop（正本）

このドキュメントは `.steering/20260117-scene-loop/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

シーン単位で生成→レビュー→再提出を反復し、整合性のある `script.md` を構築する。

## p400 Scene/Cut Design（正本）

p400 では scene を直接生成しない。
`story.md` / `visual_value.md` を読み、後続の p500 / p600 / p700 / p800 が使う scene/cut 設計へ落とす。

### p410 Scene Completion Gate

p410 は cut 作成前の scene 完成 gate である。
まず全 scene を俯瞰する抽象 review を通し、その後に scene ごとの具体 review を通す。
全 scene が合格するまで p420 へ進まない。

scene ごとに次を固定する。

- `importance`
- `target_duration_seconds`
- `estimated_duration_seconds`
- `handoff_to_next_scene`（最終 scene は `terminal_resolution`）
- `coverage_review`
  - `audience_information_covered`
  - `visualizable_action_covered`
  - `next_scene_connection_checked`
- `story_purpose`
- `audience_information`
- `withheld_information`
- `reveal_constraints`
- `affect_transition`
- `visual_value_source`
- `production_risks`
- `handoff_notes`
  - `p500_asset`
  - `p600_image`
  - `p700_narration`
  - `p800_video`

### p420 Cut Blueprint

cut ごとに次を固定する。

- `cut_role`
- `duration_intent`
- `target_beat`
- `must_show`
- `must_avoid`
- `done_when`
- `visual_beat`
- `narration_role`
- `asset_dependency_hint`

`cut_blueprint` は生成 prompt ではない。
p600 image prompt / p800 motion prompt は、この設計を元に後続 stage で作る。

## Legacy Scene Plan（最小）

- `scene_id`
- `purpose`
- `duration_seconds`
- `key_beats`
- `visual_notes`
- `audio_notes`

## フロー

`SceneIntent → AbstractSceneSetReviewLoop → ConcretePerSceneReviewLoop → OptionalHumanSceneReview → CutBlueprint → CutReviewLoop → OptionalHumanCutReview → ScriptDraft → ReviewScript → ProductionReadinessCouncil → SkeletonManifest`

旧表現でいう `ScenePlan → DraftScene → ReviewScene → (ReviseScene)* → Accept → Append` は、
現在の p400 では上記フローへ読み替える。

scene review と cut review は分ける。
抽象 scene-set review が合格するまで concrete per-scene review は走らせない。
全 scene が concrete review を通らず、かつ必要な human policy を満たしていない状態では cut を作らない。
cut authoring は scene 単位で parallel agent に分担してよいが、`script.md` と `video_manifest.md` を更新する writer は担当 `p400` L2 supervisor だけにする。

concrete per-scene review は、scene 単体の必要性だけでなく尺と接続も見る。
目標動画は最低 5-10 分程度とし、全体 scene 数と scene 重要度から scene ごとの必要尺を見積もる。
1 cut はおおよそ 4-15 秒なので、1 cut しかない scene は 4-15 秒程度にしかならない。
cinematic_story の production scene は原則 3 cut 以上、low importance scene は 2 cut 以上、high / critical scene は 5 cut 以上を基準にする。
さらに `target_duration_seconds / 12` を切り上げた cut 数を下回ってはいけない。
reviewer はこの制約を明示し、見せるべき内容が cut に全て載っているか、最終 cut が次 scene へつながるかを確認する。
つながらない場合は、cut 追加または最終 cut の増厚を要求する。
変身、発見、対決、感情反転、証拠 reveal のような spectacle beat は 1 cut に圧縮せず、setup / threshold / payoff / reaction / handoff へ分解する。

### p435 Production Readiness Council

p435 は p430 script review の後、p440 human changes / narration sync の前に走る。
Structure Auditor は骨格と因果、Duration Auditor は 5-10 分動画としての尺、Quality Auditor は映像品質と追加 scene/cut の必要性を見る。
Orchestrator は意見を統合するが、Orchestrator と auditor は設計書を編集しない。
この process 内で後段に渡る design artifacts を触れるのは Design Owner だけで、他 agent は Design Owner 向け patch brief を返す。

p435/p450 の deterministic gate が `eval.p400_readiness.status=approved` を出すまで p500 は開始しない。
この gate は target duration と cut duration 合計、script/manifest selector 対応、review report section、5 critic + aggregate の review-loop integrity を確認する。

### 反復上限

- revise は最大2回
- 超過時は人間ゲートへ昇格

## 統合規則

- accept 済みシーンのみ `script.md` に統合
- `scene_id` の順序で並べる
- p400 の L2 supervisor / bucket single writer が `script.md` を統合する
- `video_manifest.md` は `manifest_phase: skeleton` として p450 で materialize する
- p400 では asset / image / TTS / video の実行をしない

## 状態記録

`state.txt` に追記:

- `runtime.scene.<id>.status=draft|review|revise|accepted|failed`
- `runtime.scene.<id>.attempts=<n>`

## 参照

- `docs/script-creation.md`
- `docs/story-creation.md`
