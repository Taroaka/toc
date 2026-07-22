# Scene-level Loop（正本・改善版）

このドキュメントは `.steering/20260117-scene-loop/` で合意した内容を **恒久仕様として昇華**したもの。
改善版では、scene を単なる生成単位ではなく、映画の中で観客の情報・感情・期待を変化させる劇的単位として扱う。

## 目的

シーン単位で設計→レビュー→修正→統合を反復し、整合性のある `script.md` と skeleton `video_manifest.md` を構築する。
目的は「きれいな scene の列」ではなく、前段の台本から **映画のレベルで因果・感情・reveal が進む scene 群**を作ること。

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
- `dramatic_question`
- `scene_spine`
- `value_shift`
  - `from`
  - `to`
  - `visible_evidence[]`
- `causal_turn`
- `story_purpose`
- `audience_information`
- `withheld_information`
- `reveal_constraints`
- `affect_transition`
- `character_state`
  - `start`
  - `end`
  - `visible_behavior[]`
- `visual_value_source`
- `visual_thesis`
- `spatial_plan`
  - `location_id`
  - `screen_geography`
  - `continuity_anchors[]`
- `production_risks`
- `handoff_to_next_scene`（最終 scene は `terminal_resolution`）
- `story_specificity`
  - `non_compressible_beat`
  - `scene_promotion_reason`
  - `unique_scene_responsibility`
  - `actor_forces`
  - `meaning_ladder`
  - `concrete_handoff`
  - `anti_template_language`
  - `coverage_review`
    - `audience_information_covered`
    - `visualizable_action_covered`
    - `value_shift_visible`
    - `causal_turn_visible`
    - `scene_specificity_gate_passed`
    - `next_scene_connection_checked`
- `handoff_notes`
  - `p500_asset`
  - `p600_image`
  - `p700_narration`
  - `p800_video`

### p410 Review Order

1. `scene_set_review`
   - 全 scene の概要を見て、不足 scene、不要 scene、統合/分割すべき scene、順序、scene 間の因果接続を評価する。
   - scene 数は圧縮優先にしない。承認済み story の主要 beat が独立した `dramatic_question` / `value_shift` / `causal_turn` を持てるなら、まず scene として追加/分割する。
   - scene 数の上限は固定数ではなく、「これ以上 scene を増やしても既存 scene と同じ問い・同じ価値変化・同じ因果 turn しか持てず、cut 設計を厚くした方が品質が上がる」地点とする。
   - review report には、次に追加できる候補 scene と、それを scene 追加ではなく cut 増厚へ回す理由を残す。
   - `Scene Specificity Gate` として、非圧縮 beat、scene 昇格理由、固有責務、actor forces、道具/舞台装置の意味段階、concrete handoff、anti-template language を全 scene で確認する。
   - `Reveal Order Gate` として、追加/分割による早出し、欠落、順序破壊がないことを確認する。
   - `Handoff Chain Gate` として、scene 間の incoming/outgoing anchor と terminal resolution が具体的であることを確認する。
   - 1体の汎用 reviewer で見切れない場合は、複数 critic agent に分ける。少なくとも scene 数最大化を確認する `scene_count_coverage` reviewer は独立させてよい。
   - 物語の reveal が早出しされていないか、重要な感情変化が飛んでいないかを確認する。
   - この review が `approved` になるまで、per-scene review や cut blueprint へ進まない。
2. `scene_detail_review`
   - 各 scene ごとに、その scene は必要か、scene 内の情報は足りているか、後続 stage への handoff が十分かを評価する。
   - `dramatic_question` が scene 内で進むか、`value_shift` が画面で読めるか、`causal_turn` が次 scene を発生させるかを見る。
   - frontend で選択された 5-20 分の目標尺を使い、全体 scene 数と scene 重要度から、その scene に必要な尺を見積もる。
   - cut duration は選択 provider / model / input mode の capability と可視責務の密度で評価し、固定秒数から cut 数の下限を逆算しない。
   - importance や cut 数だけでは blocking finding にしない。`event_beat_inventory[]` が全 authored beat ID を exact ordered list として保持し、`must_be_seen != false` beat と distinct semantic obligation が coverage されていれば、1 cut scene も有効とする。
   - 別の具体 reviewer は次 scene も読み、現在 scene の最終 cut が次 scene へつながるかを判断する。
   - つながらない場合は、handoff が既存と異なる distinct semantic obligation なら cut 追加を提案し、同じ責務なら最終 cut を厚くする修正案を出す。
   - aggregator は `Scene Detail Gate` として scene 必要性、内部圧力、価値変化の可視性、因果 turn の可視性、隣接 scene handoff を gate 化する。
3. `scene_cinematic_gate`
   - scene が説明ではなく出来事になっているか確認する。
   - `before_state → pressure → turn → after_state` に相当する因果変化が scene 全体で読めるか確認する。これは意味上の観点であり、同名の `beat_function` や複数 beat を要求しない。
   - `visual_thesis` が p600 で描ける人物・場所・道具・光・構図に翻訳できるか確認する。
   - spectacle が物語上の誘惑/危険/報酬/喪失/発見のどれかに接続しているか確認する。

### p410 Multi-agent Review Roles

p410 の scene review は、必要に応じて複数 critic agent + aggregator に分ける。
critic は canonical artifact を編集せず、担当観点の finding と修正方針だけを report に残す。
標準の 5 critic 構成では `dramatic_structure` と `reveal_order` を同一 critic が担当する。

- `critic_1 / scene_count_coverage`: 承認済み story の主要 beat が scene として最大限展開され、非圧縮 beat と scene 昇格理由が明示されているかを見る。独立 scene 化すべき beat が既存 scene に埋もれていれば blocking finding にする。
- `critic_2 / dramatic_structure + reveal_order`: 各 scene が独立した `dramatic_question` / `value_shift` / `causal_turn` と固有責務を持つか、scene 追加/分割が reveal の早出し、欠落、順序破壊、テンプレ文への退行を起こしていないかを見る。
- `critic_3 / duration_density`: 目標尺、provider capability、distinct semantic obligation から duration risk を見て、新しい scene 責務がある場合だけ scene 追加を提案し、同じ責務なら既存 cut の増厚を選ぶ。scene 重要度や尺から cut 数の下限を作らない。
- `critic_4 / visual_production`: 追加 scene が p500 asset / p600 still / p800 motion に渡せる visible evidence、actor forces、道具/舞台装置の意味段階、visual thesis を持つかを見る。
- `critic_5 / handoff_integrity`: scene 間の因果、問い、視線・音・道具などの concrete handoff が途切れていないかを見る。
- `scene_set aggregator`: 各 critic の finding を統合し、`Scene Count Gate` / `Scene Specificity Gate` / `Reveal Order Gate` / `Handoff Chain Gate` が説明できる場合だけ `approved` を返す。
- `scene_detail aggregator`: scene 数ではなく `Scene Detail Gate` を判定し、scene 必要性、内部圧力、価値変化の可視性、因果 turn の可視性、隣接 scene handoff が説明できる場合だけ `approved` を返す。

### p410 blocking findings

次のいずれかが残る scene は p420 に進めない。

- `dramatic_question` がない。
- `value_shift.from` と `value_shift.to` が同じで、変化を示す `visible_evidence` もない。
- `causal_turn` が次 scene に影響しない。
- `visual_thesis` が抽象語だけで、画面に出る要素へ翻訳できない。
- scene が narration の説明絵でしかない。
- reveal constraints が弱く、後半で見せるべき情報を早出ししている。
- scene 数が圧縮され、独立 scene 化すべき主要 beat が既存 scene 内に埋もれている。
- `story_specificity` の 7 項目が欠けている、または `主人公は前進できるか` / `次へ進む理由が生まれる` / `光が次の場面へ運ぶ` / `価値変化の兆し` / `場所の圧力` / `主人公の姿勢と視線` のようなテンプレ文で埋められている。
- `event_beat_inventory[]` が authored `event_sequence[]` の ordered nonblank beat ID を exact に保持していない。p410 は pre-cut gate なので、`must_be_seen != false` beat / distinct semantic obligation の cut assignment はここで要求せず p420 で判定する。

### p420 Cut Blueprint

cut ごとに次を固定する。

- `cut_role`
- `cut_function`（`setup` / `pressure` / `threshold` / `turn` / `payoff` / `reaction` / `handoff` / `custom` は候補。`beat_function` の必須集合を定義しない）
- `duration_intent`
- `target_beat`
- `screen_question`
- `dramatic_job`
- `must_show`
- `must_avoid`
- `done_when`
- `visual_beat`
- `first_frame_brief`
- `motion_brief`
- `narrative_position`
- `voice_function`
- `visual_distance_policy`
- `pronunciation_targets`
- `narration_role`
- `asset_dependency_hint`

`cut_blueprint` は生成 prompt ではない。
p600 image prompt / p800 motion prompt は、この設計を元に後続 stage で作る。

### cut 分割の基準

- 1 cut は 1 意図に限定する。
- 1 cut の中で場所移動、reveal、感情反転、説明、反応を同時に背負わせない。
- cut 数は `must_be_seen != false` の authored beat と、重複を除いた distinct semantic obligation の coverage から導く。importance / target duration / 固定秒数だけでは増やさない。
- 1 authored beat と 1 distinct visual obligation を1 cutで十分に成立させられる scene は、importance に関係なく1 cutを許容する。
- 目標尺は provider capability 内の cut duration、scene duration 配分、narration / intentional silence、target runtime の見直しで満たす。同じ責務の filler cut を追加しない。
- 変身、発見、対決、感情反転、証拠 reveal のような spectacle beat は、異なる可視責務や authored event beat がある場合だけ複数 cut へ分ける。`setup` / `pressure` / `turn` / `payoff` / `threshold` / `custom` は `beat_function` の候補例であり、固定 ladder として要求しない。

### p420 cut review の観点

- 同じ `target_beat` を持つ cut が同義の責務を重複していないか。同じ authored beat を複数 cut に分ける場合も、各 cut が異なる distinct semantic obligation を持てば有効とする。
- cut 列が scene の `scene_spine` を実際に進めているか。
- `first_frame_brief` が mid-action 完了絵ではなく、動画が動き出す直前の初期状態になっているか。
- `motion_brief` が p800 専用入力として分離され、p600 image prompt authoring に漏れていないか。
- `must_show` が image / motion / narration のどこかで回収されるか。
- `must_avoid` が reveal 破りや continuity drift を防いでいるか。

### p420 Multi-agent Review Roles

p420 の cut blueprint review は、標準 5 critic + aggregator で gate 化する。
critic は canonical artifact を編集せず、担当観点の finding と修正方針だけを report に残す。

- `critic_1 / cut_intent_isolation`: 1 cut = 1 intent を確認する。場所移動、reveal、感情反転、説明、反応を 1 cut に詰め込んでいれば blocking finding にする。
- `critic_2 / scene_event_coverage`: `scene_cut_coverage_plan.event_beat_inventory[]` が `scene_event.event_sequence[]` の exact ordered nonblank `beat_id` list を保持し、そのうち `must_be_seen != false` の beat が `cut_contract.source_event_contract` に割り当てられ、任意の非空 `beat_function` が元 beat と一致し、未承認イベントを発明していないかを見る。cut_function の固定列は要求しない。`setup` / `pressure` / `turn` / `payoff` / `threshold` / `custom` は候補例にすぎず、独自 function の1 beat scene も有効である。
- `critic_3 / first_frame_motion_readiness`: `first_frame_brief` が p600 still の入力として完結し、`motion_brief` が p800 専用入力として分離されているかを見る。
- `critic_4 / multimodal_event_boundary_coverage`: `event_context_for_cut` と各 contract だけで p600 image、p700 narration、p800 motion に渡せるか、各 stage が event boundary を越えていないかを見る。
- `critic_5 / duration_density_and_handoff`: provider capability、distinct semantic obligation、target_duration、最終 cut の handoff が十分かを見る。importance や duration だけを理由に cut を増やさない。
- `aggregator`: 各 critic の finding を統合し、`Cut Blueprint Gate` の全項目が説明できる場合だけ `approved` を返す。

## Legacy Scene Plan（最小）

旧表現の `ScenePlan` は、互換上だけ次の field を許容する。
ただし p400 production では、上記の cinematic scene contract へ昇格させる。

- `scene_id`
- `purpose`
- `duration_seconds`
- `key_beats`
- `visual_notes`
- `audio_notes`

## フロー

`SceneIntent → AbstractSceneSetReviewLoop → ConcretePerSceneReviewLoop → SceneCinematicGate → OptionalHumanSceneReview → CutBlueprint → CutReviewLoop → OptionalHumanCutReview → ScriptDraft → ReviewScript → ProductionReadinessCouncil → SkeletonManifest`

旧表現でいう `ScenePlan → DraftScene → ReviewScene → (ReviseScene)* → Accept → Append` は、現在の p400 では上記フローへ読み替える。

scene review と cut review は分ける。
抽象 scene-set review が合格するまで concrete per-scene review は走らせない。
全 scene が concrete review を通らず、かつ必要な human policy を満たしていない状態では cut を作らない。
cut authoring は scene 単位で parallel agent に分担してよいが、`script.md` と `video_manifest.md` を更新する writer は担当 `p400` L2 supervisor だけにする。

### p435 Production Readiness Council

p435 は p430 script review の後、p440 human changes / narration sync の前に走る。
Structure Auditor は骨格と因果、Duration Auditor は選択された 5-20 分動画としての尺、Quality Auditor は映像品質と追加 scene/cut の必要性を見る。
Orchestrator は意見を統合するが、Orchestrator と auditor は設計書を編集しない。
この process 内で後段に渡る design artifacts を触れるのは Design Owner だけで、他 agent は Design Owner 向け patch brief を返す。

p435/p450 の deterministic gate が `eval.p400_readiness.status=approved` を出すまで p500 は開始しない。
この gate は target duration と cut duration 合計、script/manifest selector 対応、review report section、5 critic + aggregate の review-loop integrity を確認する。

### 反復上限

- 軽微な文言修正は最大2回で収束させる。
- scene 構造、reveal 順序、cut 不足、因果接続のような blocking finding は最大1 round の semantic review で検出する。
- 5 round を超えても unresolved finding が残る場合は、人間ゲートへ昇格する。

## 統合規則

- accept 済みシーンのみ `script.md` に統合する。
- `scene_id` の順序で並べる。
- p400 の L2 supervisor / bucket single writer が `script.md` を統合する。
- `video_manifest.md` は `manifest_phase: skeleton` として p450 で materialize する。
- p400 では asset / image / TTS / video の実行をしない。
- p400 は完成 image prompt を書かない。`first_frame_brief` と `p600_image_handoff` だけを残す。

## 状態記録

`state.txt` に追記:

- `runtime.scene.<id>.status=draft|review|revise|accepted|failed`
- `runtime.scene.<id>.attempts=<n>`
- `runtime.scene.<id>.cinematic_gate=passed|failed`
- `runtime.scene.<id>.blocking_findings=<n>`

## 参照

- `docs/script-creation.md`
- `docs/story-creation.md`
- `docs/implementation/image-prompting.md`
- `docs/implementation/cut-loop.md`
- `docs/implementation/cut-to-image-narration-video.md`
- `workflow/scene-outline-template.yaml`
- `workflow/cut-blueprint-template.yaml`
- `workflow/scene-conte-template.md`

## Cut Loop v2.1 Integration

p420 は、p410 で承認された scene contract を cut 列へ変換する独立 loop として扱う。既存の `cut_blueprint` は互換のため残せるが、改善版では `cut_contract` を意味上の正本にする。

追加 gate:

- `coverage_plan_complete`: scene の dramatic question / value shift / causal turn / handoff が cut に割り当てられている。
- `continuity_contract_complete`: cut 間の start/end state と carry forward が明示されている。
- `narration_contract_complete`: narration role または silent reason がある。
- `downstream_handoff_complete`: p500 / p600 / p700 / p800 への handoff がある。
- `triangulation_review_ready`: image / narration / motion の三者整合をレビューできる field がある。

p420 は「cut が生成できる」ではなく、各 cut が first-frame still、motion、narration/silence、次 cut / 次 scene への handoff へ渡せるまで完了しない。
