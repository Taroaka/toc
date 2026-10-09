# Cinematic language and observable execution

新規p410/p420は、原作・story・visual_valueから作品全体の撮影方針を一度執筆し、
`cinematic_direction.json.film_language` を正本として各sceneに渡す。
新しいp-slotや品質採点工程は追加しない。

## 入力と継承

新規作成画面の「撮影方針（任意）」は `cinematic_preferences.md` に保存する。
通常作成とscene storyboardで利用できる。空欄なら原作と演出意図からauthorが決める。
既存runの編集は、このファイルとp400の明示的な再構築を使う。完成素材を開くだけでは再執筆しない。

`film_language_v1` は `intent`、`fields`、任意の `voices` を持つ。
`fields` はpalette / lighting / exposure / optics / texture / composition / cameraの短い具体文。
`voices` は人物asset IDと安定した声質の説明を結ぶ。声質のテキスト指定は同一声の保証ではない。

film → sceneの `film_language_overrides` → cutの同名overrideの順でfieldごとに解決する。
空文字は継承、nullは任意の美術的既定値を解除する。原作の事実・光源・時間帯・開示境界を
overrideで変更できるとは扱わない。cameraの全体方針はauthorへの文脈であり、実行する動きは
cutの `camera.movement` が所有する。共通の移動指示を後から足して個別cutと衝突させない。

cacheは入力source、人物registry、撮影希望、schema、authoring policyに結び付く。
途中で希望やsourceが変わった結果は採用しない。保存済みdirectionの読込でも撮影希望のhashを確認する。

## cutの具体化

フロントの新規作成が呼ぶp420 authorは、main cutの初稿で `execution.staging` を書く。
後段の動画を見てから初めて動作順を足す運用にはしない。既存成果物へ自動追加はしない。

```yaml
staging:
  first_frame_requirements: [動作前に対象の取っ手と空いた手が見える]
  action_sequence:
    - 人物が取っ手へ手を伸ばす
    - 接触して支持を確かめてから一度だけ引く
  end_behavior:
    mode: continue  # hold / continue / exit
    description: 引く動きが続いている途中で終える
  continuity_rules: [対象の数と支持位置を保つ]
```

各行は原作とそのcutの目的から執筆する。既に向き合う人物を一括して振り向かせず、
誰が何を契機に反応するかを分ける。受け渡し・着脱・開口・支持面など、行為に必要な
前提を開始画へ用意する。便宜的な道具や物語の行為は追加しない。保持、継続、退出を
選び、`motion_end_state` と同じ到達条件を書く。静止を反復ジェスチャーで埋めない。

`first_frame_requirements` の静的条件だけが画像のposeへ投影される。動作順と終端の動作は
動画へ渡し、開始画像に先取りさせない。動画には維持する個体数・外観・物の状態も渡す。
人物なしのsub cutではstagingを使わず、既存のfirst-frame/motion/end-stateとphysicsを使う。
新しい項目はoptionalで旧runをそのまま読めるが、存在する場合は型・必須key・終端modeを検証する。
author policyをcache bindingに含め、指示更新後に旧policyのauthoring結果を無条件再利用しない。

変身・授与・出現は、まずScene Authorが原資料からbeatの `allowed_new_reveal_elements` を
執筆する。p420は割り当てbeatの許可要素だけをcutへ引き継ぎ、変化前後の数・身体・材質を
明確にする。原作にない結果をallowlistに追加しない。開始状態と終了状態の画像を混同せず、
変身途中の姿を完成後の状態として指示しない。プロンプトによる設計であり、実画像の一致や
動画の一発成功を自動保証するものではない。

新しいcutの `execution` は必要な項目だけ持つ。

```yaml
execution:
  light_continuity: 窓以外の光源を増やさず、奥の暗さを保つ
  focus:
    initial: 手前の指先に焦点
    change: 手が止まった後に顔へ焦点を移す
  performance:
    action: 相手の返答を待つ
    observable_reaction: 呼吸を止めて一度遅れて瞬く
    timing: 返答の前に一拍置く
  physics:
    - 指先が接触してから力が掛かり、抵抗の後に物が動く
  native_audio:
    mode: natural_sound
    sound_events:
      - 物が動く瞬間のきしみ
    dialogue: []
```

性能上限を超える動作を無制限に足さない。人物のいないcutには演技欄を持たせない。
演技は観察可能な行為と反応に具体化し、原作にない心理や出来事の断定に使わない。

画像には解決済みの静的な画づくりと初期焦点を渡す。焦点移動・動作・反応の時間変化は動画へ渡す。
動画では光の維持条件、物理、演技、焦点、同期音を既存のfragment groupへ追記し、明示された新欄を
固定件数で切り捨てない。由来やhashはdiagnosticsに残し、provider proseに出さない。
`cinematic_execution_v1` / `cinematic_execution_projection_v1` / `cinematic_execution_compiler_v1`
を拡張契約として記録する。旧契約の出力形式は保持する。

## 台詞と音声

標準はナレーションを中心に必要な自然音を加える。`native_audio.mode` は
`off | natural_sound | dialogue_and_sound`。旧runの未指定はoff。
台詞はspeaker_id、source_beat_ids、source_quote、text、任意のdelivery/timingで記述する。
source_quoteは参照beatの`dialogue[].text`と一致し、話者も同じ人物である必要がある。
`what_happens`や視覚的証拠などの説明文を発話へ転用しない。発話原文がないbeatでは
台詞を創作せず自然音を使う。既存のナレーション原稿を動画用台詞へ自動転用しない。

新たに同期音を要求するcutは対応するHiggsfield経路を選ぶ。native audioのON/OFFは
生成設定に明示し、非対応providerへの要求は黙って捨てない。動画に入った音は一つのmix trackとして扱う。
話者・効果音・呼吸を自動分離できるとは扱わない。

## 画面と再開

動画画面には実際に解決された撮影方針・光・焦点・演技・物理を折りたたんで表示する。
原稿や採用済み音声を表示操作で変更しない。p400の再構築には既存のcandidate/diff/applyを使う。
変更済みのrequestは再materializeし、旧生成物を新しいrequestに付け替えない。

- [Higgsfield動画API](../vendor/higgsfield.md)
- [p400](p400-cinematic-authoring.md)
- [Video prompting](video-prompting.md)
- [p860音響](sound-design.md)
- [制作補助ツール](production-tools.md)
