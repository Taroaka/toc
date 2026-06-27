# Script Creation System

台本作成システム - 物語を動画制作用の具体的な台本に変換する手順書

## 概要

このドキュメントは、`docs/story-creation.md` で設計した物語を、`docs/video-generation.md` の技術仕様に適合する具体的な台本に変換するための手順を定義する。

## Outcome Contract

Script stage のゴールは、承認済みの `story.md` を、物語意図・reveal 順序・research grounding を保ったまま
制作可能な `script.md` に変換すること。既存手順はこのゴールを満たすための作業分解として扱う。

p400 は、scene を直接画像や動画にする stage ではない。
`story.md` / `visual_value.md` から、後続の p500 asset、p600 scene implementation、p700 narration、p800 video generation が迷わない
**scene/cut 設計**を作る stage である。

### Success criteria

- 各 scene が purpose / intended affect / visual beat / narration boundary / timing / `done_when` を持つ
- 事実主張は story / research の参照に紐づき、創作補完は production 上の演出として区別されている
- p400 では narration の役割・境界・draft だけを決め、final `audio.narration.text` / `tts_text` は p700 で actual cut / image / duration に合わせて確定する
- reveal 順序、主人公、theme、承認済み human request を、無断で変更していない
- provider 固有の prompt syntax と実行管理は `video_manifest.md` 側に渡せる粒度で残っている
- p400 の時点で、各 scene が `scene intent card` を持ち、各 cut が `cut blueprint` として review できる
- 各 scene が `story_specificity` を持ち、非圧縮 beat、scene 昇格理由、固有責務、actor forces、道具/舞台装置の意味段階、具体 handoff、anti-template 判定を説明できる
- asset / image / video の実行は p400 では行わず、必要な依存関係だけを p500/p600/p800 へ渡している

### Scope boundaries

- script で決める: scene 目的、見せる情報、隠す情報、ナレーション、TTS 文字列、視覚 beat、尺の目安
- manifest へ渡す: provider prompt、asset path、生成結果、採用判定、実行 wiring
- 編集前に確認する: 事実関係、theme、主人公、reveal 順序、承認済み human request、変更禁止 scope

### p400 Cinematic Scene Design Contract（映画的 scene 契約）

p400 の scene 設計は「台本を時間で割る」作業ではなく、story の各部分を **映画で観客が体験する劇的単位**へ変換する作業である。
各 scene は、情報、感情、因果、視覚価値のいずれかを前進させる。何も変化しない scene は、短くても長くても production scene としては弱い。

#### 必須設計原則

- scene は topic ではなく event として書く。
  - 弱い: `浦島が竜宮城を見る scene`
  - 強い: `浦島が竜宮城の美しさに呑まれ、帰る意思が一時的に弱まる scene`
- scene 数は、承認済み story の主要 beat を落とさず、意味のある production scene として成立する範囲で最大化する。
  - まず不足しない方向へ scene を追加/分割し、願望の発生、拒絶、選択、変身、対決、証拠 reveal、照合、帰結のような不可逆 beat を 1 scene に圧縮しない。
  - 上限は固定数ではなく「これ以上 scene を増やしても独立した `dramatic_question` / `value_shift` / `causal_turn` を持てず、各 scene 内の cut 設計を厚くした方が品質が上がる」地点とする。
  - 追加候補の scene が既存 scene と同じ問い・同じ価値変化・同じ因果 turn しか持たない場合は、scene 追加ではなく p420 の cut 増厚で扱う。
- scene 設計では、story から scene へ落とす中間層として次の 7 項目を必須にする。
  - `non_compressible_beat`: cut に圧縮してはいけない不可逆 beat
  - `scene_promotion_reason`: beat を scene に昇格させる理由
  - `unique_scene_responsibility`: その scene だけが担う物語責務
  - `actor_forces`: 対立者、助力者、観測者など scene に圧力を与える力
  - `meaning_ladder`: 主人公、関係、道具/舞台装置の意味段階
  - `concrete_handoff`: 次 scene を発生させる具体的な物、音、視線、行為、圧力
  - `anti_template_language`: テンプレ文を避け、固有名詞・道具・関係・場所・行為で書けているか
- scene は必ず `before_state → pressure → turn → after_state` を持つ。
- scene は「観客がこの scene 中に追う問い」を持つ。問いがない scene は、単なる説明または素材集になりやすい。
- scene は `visual_thesis` を持つ。これは p600 が一枚絵として描ける scene の代表的意味であり、単なる美術説明ではない。
- scene の終点は、次 scene の起点を発生させる。`handoff_to_next_scene` が弱い scene は、cut を追加するか scene を統合する。
- reveal は早出ししない。観客に渡す情報と withheld 情報を別々に書く。
- spectacle は物語から独立した飾りではなく、誘惑、圧力、危険、発見、報酬、喪失のいずれかに接続する。

#### scene contract の必須 field

```yaml
scene_intent:
  importance: "low|medium|high|critical"
  target_duration_seconds: 24
  estimated_duration_seconds: 24
  story_purpose: "この scene が全体で進めるもの"
  dramatic_question: "この scene の間、観客が追う問い"
  scene_spine: "setup → pressure → turn → payoff → handoff の1文要約"
  value_shift:
    from: "scene開始時の状態"
    to: "scene終了時の状態"
    visible_evidence: ["画面で読める変化の証拠"]
  causal_turn: "次sceneを発生させる不可逆の出来事/決断/発見"
  audience_information: []
  withheld_information: []
  reveal_constraints: []
  affect_transition: "観客感情の変化"
  character_state:
    start: "人物の心理/関係/身体状態"
    end: "scene終了時の心理/関係/身体状態"
    visible_behavior: ["表情/姿勢/距離/手の動きなど"]
  visual_thesis: "この scene を代表する映画的な一枚絵の考え方"
  spatial_plan:
    location_id: ""
    screen_geography: "前景/中景/背景、進行方向、重要な入口/出口"
    continuity_anchors: []
  production_risks: []
  handoff_to_next_scene: "次へ渡す視覚/音/因果アンカー"
  story_specificity:
    non_compressible_beat: "この scene を cut に圧縮してはいけない不可逆 beat"
    scene_promotion_reason: "独立した問い/価値変化/因果 turn を持つため scene に昇格させる理由"
    unique_scene_responsibility: "物語全体でこの scene だけが担う責務"
    actor_forces:
      protagonist: ""
      opposing: []
      helping: []
      observing: []
      pressure_method: "誰が何によって scene 内の圧力を作るか"
    meaning_ladder:
      protagonist_stage: ""
      relationship_stage: ""
      object_or_setpiece_stage: ""
    concrete_handoff:
      incoming_trigger: ""
      outgoing_anchor: ""
      outgoing_pressure: ""
    anti_template_language:
      banned_generic_phrases_absent: false
      story_specific_terms: []
      specificity_note: ""
  scene_conflict_engine:
    desire: "scene 内で主体が欲しているもの"
    obstacle: "それを妨げる力"
    stakes: "失敗すると失うもの"
    escalation: "scene 内で圧力が上がる過程"
    no_return_point: "後戻りできなくなる瞬間"
    visible_pressure: ["画面で圧力として読めるもの"]
  audience_knowledge_delta:
    before_scene: []
    learned_during_scene: []
    still_unknown_after_scene: []
    forbidden_early_reveals: []
  handoff_chain:
    incoming: {anchor_id: "", anchor_type: "object|sound|gaze|gesture|threat|question|none", visible_or_audible_form: ""}
    outgoing: {anchor_id: "", anchor_type: "object|sound|gaze|gesture|threat|question|terminal", next_scene_selector: "", required_next_scene_start_pressure: ""}
  object_arc: []
  coverage_review:
    audience_information_covered: false
    visualizable_action_covered: false
    value_shift_visible: false
    causal_turn_visible: false
    scene_specificity_gate_passed: false
    next_scene_connection_checked: false
  handoff_notes:
    p500_asset: []
    p600_image: []
    p700_narration: []
    p800_video: []
```

#### scene を落とす blocking 条件

- `dramatic_question` がない、または scene 内で問いが進まない。
- `value_shift.from/to` が同じで、変化を示す `visible_evidence` もない。
- `causal_turn` が次 scene に影響しない。
- `visual_thesis` が抽象語だけで、画面上の人物・場所・道具・光・構図に翻訳できない。
- scene が narration の説明絵でしかなく、映像だけで読める行為や証拠がない。
- spectacle cut が物語上の誘惑/恐怖/報酬/危険/発見に接続していない。


### p400 scene/cut design slots

p400 は次の順で進める。

1. `p410 scene intent card`
   - `story.md` の scene を読み、scene ごとの物語責務を固定する
   - `visual_value.md` がある場合は、その scene の visual value / anchor / regeneration risk を読む
   - scene ごとに、観客へ渡す情報、まだ隠す情報、感情変化、根拠境界、後続 stage への注意を残す
   - scene ごとに `importance`, `target_duration_seconds`, `estimated_duration_seconds`, `handoff_to_next_scene`（最終 scene は `terminal_resolution`）, `coverage_review` を必須で残す
   - scene ごとに `story_specificity` の 7 項目を必須で残す。抽象語だけの `主人公は前進できるか`, `次へ進む理由が生まれる`, `光が次の場面へ運ぶ`, `価値変化の兆し`, `場所の圧力`, `主人公の姿勢と視線` は通さない
   - scene-set 初稿は圧縮優先にしない。主要 beat が scene として独立可能なら一度 scene 化し、review で「追加するより cut を厚くした方が良い」と説明できるところまで scene 数を増やす
   - まず抽象 scene-set review loop を回し、全 scene の追加/削除/統合/分割/順序変更/話の接続を `scene_set_review.md` と `eval.scene_set.loop.*` に記録する
   - 抽象 scene-set review は、1体の汎用 reviewer だけで見切らない。少なくとも `scene_count_coverage`, `dramatic_structure`, `reveal_order`, `duration_density`, `visual_production`, `handoff_integrity` の観点に分け、必要に応じて複数 critic agent で独立評価する
   - 標準の 5 critic 構成では、critic_1=`scene_count_coverage`, critic_2=`dramatic_structure + reveal_order`, critic_3=`duration_density`, critic_4=`visual_production`, critic_5=`handoff_integrity` として役割分担する
   - `p410b` / `p410c` は内部 review-loop label であり、scaffold の停止位置は `p410`、prompt materialize は `build-review-loop-round.py --slot p410b|p410c` で行う
   - 抽象 review が合格するまで、担当 `p400` L2 supervisor が scene 構成と transition を自動修正する
   - 抽象 review 合格後、具体 per-scene review loop を scene 単位で回し、各 scene の必要性、情報量、内部整合、handoff を `scene_detail_review.md` と `eval.scene_detail.loop.*` に記録する
   - 具体 review が合格するまで、担当 `p400` L2 supervisor が各 scene intent を自動修正する
   - human review は `gate.script_scene_review=required|optional|skipped` に従うが、agent 指摘の自動適用を都度止める gate ではない
2. `p420 cut blueprint`
   - 全 scene が `review.script.scene_set.status=approved` / `review.script.scene_detail.status=approved` / `agent_review.status=passed` を満たした後だけ cut 化する
   - cinematic_story の production scene は原則 3 cut 以上に分ける。low importance scene だけ 2 cut を許容し、high は 5 cut 以上、critical は 7 cut 以上を必須目安にする
   - `target_duration_seconds` が長い scene は `ceil(target_duration_seconds / 8)` を下回らない。reference / title / pure transition のような例外は理由を残す
   - cut 数と cut 役割は固定 template で決めない。scene の不可逆な story event、因果証明、観客理解差分、必要な人物役割を列挙し、それを画で証明するために必要な cut へ逆算する
   - scene 単位で並列 agent に分担してよいが、`script.md` は担当 `p400` L2 supervisor が bucket single writer として統合する
   - 1 cut は 1 意図に限定する。1 cut の中で場所移動、reveal、感情反転、説明を同時に背負わせない
   - spectacle / transformation / emotional reversal / proof reveal は 1 cut に圧縮しない。ただし `setup / pressure / threshold / turn / payoff / reaction / handoff` は候補ラベルであり、scene ごとの必要性に従って使う
   - cut ごとに `target_beat`, `audience_knowledge_delta`, `causal_proof`, `visual_evidence`, `required_roles`, `must_show`, `must_avoid`, `done_when`, `visual_beat`, `first_frame_brief`, `narration role`, `asset dependency hint` を書く
   - cut blueprint の agent review loop を回し、`cut_blueprint_review.md` と `eval.cut_blueprint.loop.*` に記録する
   - cut blueprint review は、critic_1=`cut_intent_isolation`, critic_2=`scene_event_coverage`, critic_3=`first_frame_motion_readiness`, critic_4=`multimodal_event_boundary_coverage`, critic_5=`duration_density_and_handoff` を標準割当とする
   - aggregator は `Cut Blueprint Gate` を持ち、1 cut = 1 intent、beat ladder coverage、first frame / motion readiness、multimodal contract、duration / handoff が説明できる場合だけ `approved` にする
   - human review は `gate.script_cut_review=required|optional|skipped` に従う
3. `p430 script review`
   - `script.md` を正本として、scene/cut loop 後の最終集約 review を行う
   - facts / theme / protagonist / reveal order / approved human requests を無断変更していないか確認する
   - cut 数、尺、visual/narration の距離、説明過多、asset 依存の抜けを確認する
4. `p435 production readiness council`
   - p430 合格後、p440 human changes / narration sync の前に `production_readiness_review.md` を作る
   - Structure Auditor は script の骨格、因果、scene/cut 接続、破綻を評価する
   - Duration Auditor は cut 数と台本から 5-10 分動画の尺を予測し、1 cut = 4-15 秒前提で不足を特定する
   - Duration Auditor は `video_manifest.md.video_metadata.target_duration_seconds` と production cut duration 合計を比較し、90% 未満なら passed にしてはいけない。p700 へ defer してはいけない
   - Quality Auditor は尺/骨格の弱点から scene/cut 追加、cut 増厚、映像品質改善を提案する
   - Orchestrator は各 auditor の意見を統合し、Design Owner 向け patch brief にする
   - Orchestrator と auditor は意見側であり、後段で使われる設計書を編集しない。この p435 process 内で downstream design artifacts を触れるのは Design Owner だけとする
   - p500 へ進むには `eval.p400_readiness.status=approved` が必要で、scene/cut/review/duration/selector 対応の deterministic gate が 1 つでも落ちたら p500 grounding は開始しない
5. `p450 skeleton manifest`
   - `script.md` から `video_manifest.md` を `manifest_phase: skeleton` として materialize する
   - skeleton manifest は scene/cut selector、正本 `cut_contract`、旧 reader 用 `scene_contract` alias、asset id placeholder、image/audio/video の実行枠を持つ
   - final image prompt、asset 生成、TTS 実行、motion prompt の確定は後続 stage に渡す

### p410 Scene Intent Card

各 scene は、少なくとも次を持つ。

```yaml
scene_intent:
  importance: "low|medium|high|critical"
  target_duration_seconds: 24
  estimated_duration_seconds: 24
  story_purpose: "この scene が物語全体で担う役割"
  dramatic_question: "この scene の間、観客が追う問い"
  scene_spine: "setup → pressure → turn → payoff → handoff の1文要約"
  value_shift:
    from: "scene開始時の状態"
    to: "scene終了時の状態"
    visible_evidence: ["画面だけで変化が読める証拠"]
  causal_turn: "次 scene を発生させる不可逆の出来事/決断/発見"
  audience_information: ["この scene で観客に渡す情報"]
  withheld_information: ["この scene ではまだ見せない情報"]
  reveal_constraints: ["初出や早出しを避ける対象"]
  affect_transition: "前 scene からの感情変化"
  character_state:
    start: "人物の心理/関係/身体状態"
    end: "scene終了時の心理/関係/身体状態"
    visible_behavior: ["表情/姿勢/距離/手の動きなど"]
  visual_value_source: "visual_value.md の対応 part / none"
  visual_thesis: "この scene を代表する映画的な一枚絵"
  spatial_plan:
    location_id: ""
    screen_geography: "前景/中景/背景、入口/出口、進行方向"
    continuity_anchors: []
  production_risks: ["後続 stage で崩れやすい点"]
  handoff_to_next_scene: "次 scene へつなぐ視覚/音/因果アンカー。最終 scene は terminal_resolution"
  story_specificity:
    non_compressible_beat: "この scene を cut に圧縮してはいけない不可逆 beat"
    scene_promotion_reason: "独立した問い/価値変化/因果 turn を持つため scene に昇格させる理由"
    unique_scene_responsibility: "物語全体でこの scene だけが担う責務"
    actor_forces:
      protagonist: ""
      opposing: []
      helping: []
      observing: []
      pressure_method: "誰が何によって scene 内の圧力を作るか"
    meaning_ladder:
      protagonist_stage: ""
      relationship_stage: ""
      object_or_setpiece_stage: ""
    concrete_handoff:
      incoming_trigger: ""
      outgoing_anchor: ""
      outgoing_pressure: ""
    anti_template_language:
      banned_generic_phrases_absent: false
      story_specific_terms: []
      specificity_note: ""
  scene_conflict_engine:
    desire: "scene 内で主体が欲しているもの"
    obstacle: "それを妨げる力"
    stakes: "失敗すると失うもの"
    escalation: "scene 内で圧力が上がる過程"
    no_return_point: "後戻りできなくなる瞬間"
    visible_pressure: ["画面で圧力として読めるもの"]
  audience_knowledge_delta:
    before_scene: []
    learned_during_scene: []
    still_unknown_after_scene: []
    forbidden_early_reveals: []
  handoff_chain:
    incoming: {anchor_id: "", anchor_type: "object|sound|gaze|gesture|threat|question|none", visible_or_audible_form: ""}
    outgoing: {anchor_id: "", anchor_type: "object|sound|gaze|gesture|threat|question|terminal", next_scene_selector: "", required_next_scene_start_pressure: ""}
  object_arc: []
  coverage_review:
    audience_information_covered: false
    visualizable_action_covered: false
    value_shift_visible: false
    causal_turn_visible: false
    scene_specificity_gate_passed: false
    next_scene_connection_checked: false
  handoff_notes:
    p500_asset: ["asset 化すべき候補"]
    p600_image: ["still prompt で守るべき visual proof / 初期状態"]
    p700_narration: ["ナレーションで補うこと / 補わないこと"]
    p800_video: ["motion で守ること"]
```

### p420 Cut Blueprint

各 cut は、少なくとも次を持つ。

```yaml
cut_blueprint:
  cut_role: "main|sub|transition|reaction|visual_payoff"
  cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
  duration_intent: "short|standard|hold"
  target_beat: "この cut で伝える 1 つのこと"
  screen_question: "この cut の間、観客が画面から読む問い"
  dramatic_job: "scene 全体の pressure / turn / payoff のどこを担当するか"
  audience_knowledge_delta: "この cut で観客の理解がどう進むか"
  causal_proof: "原因と結果が画面上でどう同時に読めるか"
  visual_evidence: ["因果を証明する画面内証拠"]
  required_roles: ["protagonist|opponent|helper|witness|authority_or_community"]
  source_event_contract:
    primary_event_beat_id: "scene1_event_setup"
    source_event_beat_ids: ["scene1_event_setup"]
    event_beat_function: "setup"
    event_time_position: "before_trigger"
  anti_redundancy_key: "同義反復を検出するための意味キー"
  must_show: ["画・音・動きのどこかで必ず見せるもの"]
  must_avoid: ["drift / reveal 破り / 説明過多など"]
  done_when: ["reviewer が完了判断できる条件"]
  visual_beat: "画として何が見えるか"
  first_frame_brief: "動画が動き出す直前に見えている初期状態。prompt本文には制作メタを書かない"
  static_first_frame_rule: "動きではなく静止画として何を証明するか"
  motion_brief: "p800 motion prompt 専用。p600 image prompt authoring では参照しない"
  narrative_position: "opening|middle|ending"
  voice_function: "information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence"
  visual_distance_policy: "stay_close|contextual|meaning_first|silent"
  pronunciation_targets: []
  narration_role: "setup|fact|emotion|contrast|aftertaste|silent"
  asset_dependency_hint:
    character_ids: []
    object_ids: []
    location_ids: []
    reusable_still_candidates: []
```

`cut_blueprint` は生成 prompt ではない。
API にそのまま渡す文面は p600 / p800 で作る。

### p410 Review Order

p410 の review は抽象から具体へ進む。

1. `scene_set_review`
   - 全 scene の概要を見て、不足 scene、不要 scene、統合/分割すべき scene、順序、scene 間の話の接続を評価する
   - scene 数は、意味のある scene として成立する範囲で最大化されているかを評価する
   - 「次に追加できる scene は何か」「それを追加せず cut 増厚で扱う理由は何か」を説明できない場合は `approved` にしない
   - `scene_count_coverage` reviewer は、承認済み story の主要 beat が既存 scene に埋もれていないかを専門に見る
   - `dramatic_structure` reviewer は、各 scene が独立した問い・価値変化・因果 turn を持つかを見る
   - `reveal_order` reviewer は、追加/分割した scene が reveal の早出しや欠落を起こしていないかを見る
   - `duration_density` reviewer は、全体尺・scene 重要度・cut 数から、scene 追加と cut 増厚のどちらが品質に効くかを見る
   - `visual_production` reviewer は、追加 scene が後段 p500/p600/p800 で実際に映像化できる visible evidence を持つかを見る
   - `handoff_integrity` reviewer は、scene 間の因果と handoff が途切れていないかを見る
   - aggregator は全 reviewer の finding を統合し、`Scene Count Gate`、`Scene Specificity Gate`、`Reveal Order Gate`、`Handoff Chain Gate` が説明できる場合だけ `approved` にする
   - 標準 5 critic では `dramatic_structure` と `reveal_order` を同一 critic が担当してよいが、report では判定を分ける
   - この review が `approved` になるまで、per-scene review や cut blueprint へ進まない
2. `scene_detail_review`
   - 各 scene ごとに、その scene は必要か、scene 内の情報は足りているか、後続 stage への handoff が十分かを評価する
   - 目標動画は最低でも 5-10 分程度を想定し、全体 scene 数と scene 重要度から、その scene に必要な尺を見積もる
   - 1 cut はおおよそ 4-15 秒であり、cut が 1 つしかない scene は 4-15 秒程度の尺しか持てないことを明示して評価する
   - medium 以上の scene が 2 cut だけで済んでいる場合は、情報量・感情変化・次 scene への接続のどれかを失っていないかを blocking finding として扱う
   - この scene で見せるべき内容が、予定 cut ですべて表現されているか確認する
   - 別の具体 reviewer は次 scene も読み、現在 scene の最終 cut が次 scene へつながるかを判断する
   - つながらない場合は、もう 1 cut 追加するか、最終 cut を厚くする修正案を出す
   - 全 scene の `agent_review.status=passed` が揃うまで cut blueprint へ進まない
   - aggregator は `Scene Detail Gate` として scene 必要性、内部圧力、価値変化の可視性、因果 turn の可視性、隣接 scene handoff を確認し、未解決なら `approved` にしない

### Subagent use

- scene draft、scene-set review、scene-detail review、narration draft、script review は scene / cut / review 観点単位で contextless subagent に任せてよい
- scene-set review は複数 subagent を推奨する。少なくとも `scene_count_coverage` は独立させ、scene 数を最大化せず圧縮した案が通らないようにする
- 1つの subagent に全観点を背負わせる場合でも、出力には `scene_count_coverage`, `dramatic_structure`, `reveal_order`, `duration_density`, `visual_production`, `handoff_integrity` の各判定を分けて残す
- subagent には `story.md`、`visual_value.md`、stage readset、担当 scene / cut、出力先 scratch path だけを渡す
- `script.md`、skeleton `video_manifest.md`、human change の採否、`subagent_trace` は担当 `p400` L2 supervisor が統合する

### 位置づけ

```
[情報収集] → [物語生成] → [視覚価値設計] → [台本作成] → [動画生成]
                                          ↑ 本書
```

### 入力

- `output/stories/{topic}_{timestamp}.md` - 物語スクリプト（story-creation.md出力）
- `output/<topic>_<timestamp>/visual_value.md` - p300 visual planning 正本（あれば参照。visual identity / scene visual value / anchor / reference strategy / asset candidates / regeneration risks / handoff を含む）
- 物語構造、感情曲線、エンゲージメント設計
- `docs/affect-design.md` - Russell 系の valence / arousal 補助レイヤー
- `docs/video-generation.md` - 汎用の動画生成原則
- `workflow/playbooks/video-generation/kling.md` - `kling_3_0` / `kling_3_0_omni` 利用時の専用 prompt guide

### 出力

- `output/scripts/{topic}_{timestamp}.md` - 制作用台本
- キャラクター設計、シーン詳細、タイムライン

---

## Legacy Short-form Template（非正本）

以下の第1章以降には、旧 60 秒動画、固定 8 scene、`text_overlay`、p400 時点の final narration / `tts_text` などの短尺テンプレートが残っている。
これは互換・参照用の legacy short-form template であり、`cinematic_story` の正本ではない。新規の映画的 story run では、上記の p400 Cinematic Scene Design Contract、p410 scene_set/detail gate、p420 cut contract を canonical とする。

## 第1章：台本の役割と原則

### 1.1 物語と台本の違い

```
[物語 (Story)]                    [台本 (Script)]
・抽象的な構造                    ・具体的な指示書
・「何を伝えるか」                ・「どう見せるか」
・感情の設計図                    ・制作の設計図
・物語パターン別                  ・全物語共通フォーマット
```

**台本の役割**: 物語の意図を、映像・音声・テキストの具体的指示に翻訳する。

### 1.2 共通フォーマットの必要性

異なる物語パターン（隠された真実型、逆説型、謎解き型など）でも、動画制作に必要な情報は共通している：

| 必須要素 | 説明 |
|---------|------|
| **登場人物** | 誰が出るか、どう見えるか |
| **場面設定** | どこで、いつ |
| **視覚指示** | 何を映すか、どう動かすか |
| **音声指示** | 何を話すか、どんなBGMか |
| **時間配分** | 各要素の尺 |

### 1.3 台本作成の3原則

1. **具体性**: 「感動的な場面」ではなく「涙を流す主人公のクローズアップ」
2. **再現性**: 誰が読んでも同じ映像をイメージできる
3. **制作可能性**: 技術的に実現可能な指示のみ

### 1.3.1 Provider 別の prompt 参照先

- 通常は `docs/video-generation.md` の汎用原則に合わせて、後続の動画 prompt を逆算する
- `video_generation.tool` が `kling_3_0` / `kling_3_0_omni` の場合、動画 prompt を書く agent は
  **通常の動画生成ガイドの代わりに** `workflow/playbooks/video-generation/kling.md` を prompt 設計の正本として使う
- ただし、運用原則・品質保証・一貫性管理などの全体方針は引き続き `docs/video-generation.md` を参照する

### 1.4 視覚化価値パートの扱い

`visual_value.md` がある場合、Scriptwriter はそれを
**visual planning 正本** として読み、scene / cut skeleton が守る visual value を script に取り込む。

基本ルール:

- `global_visual_identity` と `scene_visual_values[]` を、台本の視覚方針と scene/cut skeleton に反映する
- `anchor_cut_candidates[]` は、後続 manifest / asset stage が判断できるよう selector と意図を残す
- `asset_bible_candidates` は、p500 の `asset_plan.md` で materialize できるよう使用箇所を保つ
- `reference_strategy` と `regeneration_risks[]` は、human change や later prompt authoring で失われないようにする
- `value_parts[]` がある場合だけ、中盤の silent visual payoff として扱う

silent visual payoff の互換ルール:

- 配置は動画全体の `20% - 80%`
- 1パート `4-6` カット
- 各カット `4` 秒
- ナレーションなし
- 文字説明ではなく、映像だけで満足感を作る

これは本筋を止める寄り道ではなく、
視聴者に「この題材だからこそ見たいもの」を与えるための設計とする。

### 1.5 Script Evaluator Contract

台本にも evaluator と共有する契約を置く。

```yaml
evaluation_contract:
  target_arc: "opening,development,climax"
  must_cover: ["主人公の目的", "転機"]
  must_avoid: ["TODO", "未定"]
  done_when: ["主要 phase が揃う", "各 scene が research を参照する"]
  success_criteria:
    - "視聴者が外部説明なしに scene goal を理解できる"
    - "事実主張が story / research へ追跡できる"
    - "創作補完が明示され、research と矛盾していない"
    - "承認済みの reveal 順序や scope を無断変更していない"
  scope_boundaries:
    can_change: ["scene wording", "visual specificity", "timing within target duration"]
    ask_before_changing: ["facts", "theme", "protagonist", "reveal order", "approved human requests"]
  reveal_constraints:
    - subject_type: "character"
      subject_id: "guide_princess"
      rule: "must_not_appear_before"
      selector: "scene12_cut01"
      rationale: "驚きや登場の効果を守るため、初出タイミングを script 側で固定する"
```

evaluator は少なくとも次を確認する。

- `must_cover` が script に現れているか
- `must_avoid` が残っていないか
- `target_arc` に指定した phase が scene に存在するか
- `reveal_constraints` に反する初出 / 早出しが scene plan 上で起きていないか
- scene ごとの具体性と research grounding が十分か

### 1.6 Human Review Source Of Truth

ナレーション文面の human review は `script.md` を正本にする。

- reviewer はまず `script.md` を見る
- 確定後、`video_manifest.md` の `audio.narration.*` へ一方向同期する
- manifest 側で直接ナレーション文面を育てない

`script.md` の ElevenLabs 正本は `elevenlabs_prompt` と `tts_text` の組とする。
この slice では runtime 側の contract は変えないが、script 側では `tts_text` を
**ElevenLabs v3 に渡す最終文字列**として扱う。

cut ごとに少なくとも次を持てる。

```yaml
elevenlabs_prompt:
  spoken_context: "string"
  voice_tags: ["excited", "laughs harder"]
  spoken_body: "string"
  stability_profile: "creative|natural|robust|\"\""
tts_text: "string"
human_review:
  status: "pending|approved|changes_requested"
  notes: ""
  change_requests:
    - request_id: "hr-001"
      status: "open|accepted|rejected|deferred|resolved"
      category: "naturality|reveal|pronunciation|story_alignment|timing|other"
      requested_change: ""
      rationale: ""
      suggested_narration: ""
      suggested_tts_text: ""
      requested_at: "ISO8601"
      resolved_at: ""
      resolution_notes: ""
  approved_narration: ""
  approved_tts_text: ""
```

- `elevenlabs_prompt`
  - `tts_text` を組み立てるための authoring source
  - `spoken_context` / `voice_tags` / `spoken_body` / `stability_profile` を持つ
  - `voice_tags` は bracket なしの生タグを順序付き配列で持つ
- `narration`
  - 作品として読ませる台本文面
- `tts_text`
  - ElevenLabs v3 に送る final string
  - 組み立て順は `spoken_context + [tag][tag] + spoken_body`
  - 通常はひらがな寄せを基本にしつつ、`[]` の audio tag を許容する
  - ElevenLabs v3 で音声品質を優先する cut では、漢字かな交じりの自然な日本語を許可する
  - 締め / 教訓 / bitter aftertaste の narration では、`spoken_context` は原則空にし、`voice_tags: ["low", "measured"]` を基準にする
  - 採用基準例: `[low][measured] 知らない世界には、強い引力があります。`
- `human_review.approved_narration`
  - 人間が確定した文面。空なら `narration` を使う
- `human_review.approved_tts_text`
  - 人間が確定した読み上げ文面。空なら `tts_text` を使う
- `human_review.change_requests[]`
  - reviewer が出した個別の修正要求
  - `status: open` が残っている間は `human_review.status` を `approved` にしない
  - `approved_*` field は open request の代替ではなく、解消後に採用した値を残す

運用ルール:

- reviewer が差し戻すときは、`notes` だけで終わらせず `change_requests[]` に分解して残す
- reveal 順序、かな読み、意味距離、説明過多のように論点が複数ある場合は request を分ける
- `changes_requested` はレビューの結果、`change_requests[]` は要求の本文であり、役割を混同しない
- `elevenlabs_prompt` を修正したら、同じ変更を `tts_text` にも反映する
- `elevenlabs_prompt` 用の `approved_*` mirror field は追加しない
- `spoken_context` は読み上げ対象なので、音声品質や尺を優先する cut では使わない
- `alpha` は常用 baseline にしない。輪郭や押し出しが必要な cut に限定する
- 導入 / 通常 narration は `gentle` 系、締め / 教訓 narration は `low + measured` 系を優先する

人間 review の観点は固定しておく。

- 昔話 / 作品文脈として自然か
- reveal 順序を壊していないか
- ElevenLabs v3 の final text と audio tag で違和感がないか
- 映像より先走っていないか
- 説明過多になっていないか

human review が visual / asset / image / video まで踏み込む場合は、`script.md` top-level の `human_change_requests[]` を正本にする。

```yaml
human_change_requests:
  - request_id: "hr-001"
    source: "human_script_review"
    created_at: "ISO8601"
    raw_request: "scene 追加、asset 参照、video direction 変更"
    original_selectors: ["scene3_cut2"]
    current_selectors: ["scene3.1_cut2.1"]
    normalized_actions: []
    status: "pending|normalized|applied|verified|waived"
    resolution_notes: ""
    applied_manifest_targets: []
```

- raw request は削らない
- 後段で扱うために `normalized_actions[]` へ分解する
- `update_scene_contract` を使って `target_beat / must_show / must_avoid / done_when` を追従更新してよい
- `scene_id` / `cut_id` は dotted numeric string を許可する
- renumber しても `original_selectors[]` と `current_selectors[]` を残す
- asset に関する指示は、後段の `asset_plan.md` で materialize される前提で `source_script_selectors[]` を辿れるように残す

### 1.6.1 Script と Manifest の責務境界

`script.md` は **物語と映像意図の正本**、`video_manifest.md` は **生成実装の正本** とする。

- `script.md` が持つもの
  - `scene_summary`
  - `visual_beat`
  - reveal 順序
  - `narration`
  - `elevenlabs_prompt`
  - `tts_text`
  - 人レビューで来た image/video 指示
- `script.md` が持ちすぎないもの
  - provider 固有 prompt 文法
  - 実行パラメータ
  - 依存解決済みの asset wiring 全体

原則:

- `script.md` は image/video をまったく語らない文書にはしない
- ただし、image/video の **生成方法そのもの** を主責務にしない
- `tts_text` は TTS 専用の final string であり、image/video generation の主ソースにしない

したがって、`script.md` は「何を見せるか」「何をまだ見せてはいけないか」「人レビューでどの参照画像や演出意図が入ったか」を保持し、`video_manifest.md` がそれを prompt / asset / motion / continuity へ materialize する。

ただし reusable asset の設計は cut stage より前に独立して扱ってよい。asset に関する human request は、まず `asset_plan.md` に集約し、その review / approve 後に asset を生成し、cut stage がそれを参照する。

### 1.7 Narration Distance Policy

`narration` と `visual_beat` は、常に差を作るのでも、常に一致させるのでもなく、**scene の役割**で距離を決める。

基本方針:

- 序盤 / 中盤
  - 視聴者を物語の中へ入れることを優先
  - `narration` は `visual_beat` に基本的に沿ってよい
  - 異界・地下都市・聖域・夢の中の城のような **非日常感のあるエリア** では、体感描写だけに寄せすぎない
    - 対象読者は現実に生きている人なので、「ここは現実とは違う世界だ」「ありえない広さだ」のように、非日常性をダイレクトに説明してよい
    - 説明重視にする場合も、reveal 順序（誰をまだ見せないか / 何をまだ言わないか）は守る
- 終盤
  - 必ず差を作る必要はない
  - まだ没入維持が必要なら、近いままでよい
  - 意味や代償を残したい cut だけ、`narration` が `visual_beat` を少し超えてよい

理想は「映像のあとに意味が残る一文」が入ることだが、それは **常時必須ではなく、文脈依存** とする。

#### 結末型の考慮

作品ごとに終わり方は違うため、script 設計では結末型も意識する。

- `happy`
- `bittersweet`
- `tragic`
- `cautionary`
- `ambiguous`

たとえば浦島太郎は、単純な happy end ではなく、代償や喪失の重さが残る物語として扱う。
この場合、帰還以後の narration は必要に応じて次を価値化してよい。

- 何を失ったのか
- なぜそれが重いのか

#### 推奨 field

必要なら script に次の補助 field を置いてよい。

```yaml
script_metadata:
  ending_mode: "happy|bittersweet|tragic|cautionary|ambiguous"

scenes:
  - scene_id: 15
    narration_distance_policy: "stay_close|contextual|meaning_first"
    narrative_value_goal:
      mode: "immersion|meaning|mixed"
      leave_viewer_with: ["何を失ったのか", "なぜそれが重いのか"]
```

- `stay_close`
  - `narration` は `visual_beat` に沿う
- `contextual`
  - 沿ってもよいし、少し意味を足してもよい
- `meaning_first`
  - 映像を見たあとに意味が残る一文を優先する

---

## 第2章：キャラクター設計（ペルソナ）

### 2.1 ペルソナ設計の目的

動画全体でキャラクターの一貫性を保つための詳細設計。

```
[story-creation.md]              [本書で追加]
・主人公の役割                   ・外見の詳細
・物語上の機能                   ・視覚的特徴
・変容の軌跡                     ・固定プロンプト
```

### 2.2 ペルソナテンプレート

```yaml
# === キャラクターペルソナ ===
characters:
  - character_id: "protagonist"
    name: "主人公名"
    role: "主人公 | 語り手 | 対象者 | サポート"

    # --- 物語上の役割（story-creation.mdから継承）---
    narrative_function:
      ordinary_world: "日常での状態・立場"
      desire: "何を望んでいるか"
      flaw: "克服すべき弱点・課題"
      transformation: "どう変容するか"

    # --- 視覚的詳細（本書で設計）---
    visual_identity:
      # 顔の特徴（AI生成で一貫性を保つための固定記述）
      face:
        shape: "oval | round | square | heart | long"
        eyes: "色、形、特徴"
        hair: "色、長さ、スタイル"
        distinguishing_features: "ほくろ、眉の形など"

      # 体格
      body:
        height: "tall | medium | short"
        build: "slim | average | athletic | heavy"
        posture: "姿勢の特徴"

      # 服装（デフォルト）
      default_outfit:
        top: "具体的な記述"
        bottom: "具体的な記述"
        footwear: "具体的な記述"
        accessories: "アクセサリー類"

      # 場面別服装（必要な場合）
      outfit_variations:
        - scene_context: "日常シーン"
          outfit: "カジュアルな服装の詳細"
        - scene_context: "クライマックス"
          outfit: "変化した服装の詳細"

    # --- AI生成用固定フレーズ ---
    fixed_prompts:
      face: "oval face with dark brown eyes, short black hair with slight wave"
      body: "medium height, slim build"
      outfit: "navy blue hoodie over white t-shirt, dark jeans"
      style: "realistic, cinematic lighting"

    # --- 参照画像 ---
    reference_images:
      - path: "assets/characters/{character_id}_front.png"
        view: "front"
      - path: "assets/characters/{character_id}_side.png"
        view: "side"
      - path: "assets/characters/{character_id}_expression.png"
        view: "emotional_range"

    # --- 声の設定（ナレーション/セリフがある場合）---
    voice:
      tone: "落ち着いた | 元気 | 知的 | 情熱的"
      speed: "slow | normal | fast"
      tts_voice_id: "elevenlabs_voice_id or openai_voice_name"
```

### 2.3 ペルソナ設計チェックリスト

```yaml
persona_checklist:
  visual_completeness:
    - face_described: true/false
    - body_described: true/false
    - outfit_described: true/false
    - fixed_prompts_created: true/false

  narrative_alignment:
    - matches_story_role: true/false
    - transformation_visible: true/false  # 変容が視覚的に表現可能か

  technical_feasibility:
    - ai_generatable: true/false  # AI生成で再現可能な記述か
    - consistency_testable: true/false  # 一貫性をチェック可能か
```

### 2.4 複数キャラクターの区別

複数のキャラクターがいる場合、明確な視覚的差別化が必要：

```yaml
character_differentiation:
  strategy: "contrast"  # 対照的な要素で区別

  protagonist:
    color_palette: "暖色系（青、緑）"
    silhouette: "スリム、動的"

  antagonist:
    color_palette: "寒色系（赤、黒）"
    silhouette: "重厚、静的"

  visual_contrast:
    - element: "hair_color"
      protagonist: "black"
      antagonist: "silver"
    - element: "outfit_style"
      protagonist: "casual, modern"
      antagonist: "formal, traditional"
```

---

## 第3章：シーン構成設計

### 3.1 シーン分解の基本

物語構造をシーン単位に分解する：

```
[物語構造]              →  [シーン分解]
日常世界 (0-10%)           Scene 1: オープニング
冒険への召命 (10-15%)      Scene 2: 問題提示
試練 (15-55%)              Scene 3-5: 展開・葛藤
変容 (55-85%)              Scene 6-7: クライマックス・転換
帰還 (85-100%)             Scene 8: エンディング
```

### 3.2 シーンテンプレート

```yaml
# === シーン詳細 ===
scenes:
  - scene_id: 1
    scene_name: "オープニング - 日常世界"

    # --- タイミング ---
    timing:
      position_percent: "0-10"
      duration_seconds: 6  # 60秒動画の場合
      timestamp: "00:00-00:06"

    # --- 物語上の機能 ---
    narrative:
      phase: "ordinary_world"
      purpose: "視聴者を引き込み、主人公に共感させる"
      hook_type: "question | statement | shock | emotion"
      emotional_target: "curiosity"  # この時点で狙う感情

    # --- 感情座標（任意） ---
    affect:
      intended:
        valence: -1.0..1.0
        arousal: 0.0..1.0
        label_hint: "curiosity | awe | dread | relief"
        audience_job: "hook | bond | strain | release | aftertaste"
        contrast_from_previous: "lift | drop | spike | settle | invert"

    # --- 視覚価値パート（任意）---
    visual_value:
      source_part_id: "optional"
      role: "visual_payoff | none"
      narration_policy: "spoken | silent"
      placement_guard: "20-80%"

    # --- シーン目的（G.O.D.D.）---
    scene_goal:
      goal: "シーン内で主人公が達成したいこと"
      obstacle: "外的/内的の障害"
      dilemma: "簡単に選べない選択肢の葛藤"
      decision: "主人公が下す決断（次シーンへ影響）"

    # --- シーン内ミニ構造 ---
    micro_structure:
      beats:
        - "Establish the scene"
        - "Catalyst"
        - "Rising action"
        - "Climax"
        - "Aftermath"
      value_shift: "シーン内で起きる変化（価値の移動）"

    # --- Show, don’t tell チェック ---
    show_dont_tell:
      visual_first: true
      action_supports_narration: true
      lines_without_visual_support: 0

    # --- 登場キャラクター ---
    characters:
      - character_id: "protagonist"
        action: "具体的な行動"
        expression: "表情・感情状態"
        position: "画面上の位置（center, left, right）"

    # --- 視覚指示 ---
    visual:
      location:
        setting: "場所の説明"
        time_of_day: "morning | afternoon | evening | night"
        weather: "天候・雰囲気"
        props: "小道具リスト"

      shot:
        type: "wide | medium | close-up | extreme_close-up"
        angle: "eye_level | low_angle | high_angle | dutch_angle"
        movement: "static | pan_left | pan_right | zoom_in | zoom_out | tracking"
        duration: 3  # このショットの秒数

      composition:
        rule_of_thirds: "主要被写体の位置"
        depth: "前景・中景・背景の要素"
        lighting: "照明の方向・質感"

      # p600 への画像設計 handoff
      # p400 では完成 prompt を書かない。ここでは「何を描くべきか」の意味と画面証拠だけを残す。
      p600_image_handoff:
        visual_thesis: "この scene を代表する一枚絵の考え方"
        first_frame_brief: "動画が動き出す直前に見えている初期状態"
        subject_priority: ["最優先で読ませる人物/物/場所"]
        screen_evidence: ["観客が画面だけで理解できる証拠"]
        blocking_notes: "前景/中景/背景、視線、距離、入口/出口"
        lighting_notes: "感情と reveal に対応する光"
        forbidden_prompt_metadata:
          - "scene_id / cut_id"
          - "物語タイトルだけでの説明"
          - "最初の1フレーム / first frame という制作メタ"

    # --- 音声指示 ---
    audio:
      narration:
        text: "ナレーションの完全なテキスト"
        timing: "sync | voiceover"
        emotion: "読み方の感情指示"

      dialogue:  # キャラクターのセリフがある場合
        - character_id: "protagonist"
          line: "セリフテキスト"
          timing: "00:02-00:04"

      bgm:
        track: "BGMトラック名 or 説明"
        mood: "mysterious | uplifting | tense | melancholic"
        volume: 0.3  # 0.0-1.0
        fade: "fade_in | fade_out | crossfade | none"

      sfx:
        - effect: "効果音の説明"
          timing: "00:01"
          volume: 0.5

    # --- テキストオーバーレイ ---
    text_overlay:
      main_text:
        content: "メインテロップ"
        position: "bottom_center | top_center | center"
        style: "subtitle | title | emphasis"
        timing: "00:01-00:05"

      sub_text:
        content: "補助テキスト"
        position: "bottom_left"
        timing: "00:02-00:04"

    # --- トランジション ---
    transition:
      to_next_scene: "cut | fade | dissolve | wipe"
      duration: 0.5  # トランジションの秒数
```

### 3.2.1 映画的 scene の内部構造

scene は cut の集合ではなく、cut を束ねる劇的な流れを持つ。
標準形は次の 5 段階で考える。

```yaml
cinematic_scene_structure:
  setup: "場所・人物状態・観客の問いを立てる"
  pressure: "欲望/障害/危険/誘惑を画面上で強める"
  threshold: "引き返せない一歩の直前を見せる"
  turn: "発見/決断/失敗/反転など、sceneの価値が変わる瞬間"
  payoff_or_handoff: "変化の結果、または次sceneへの未解決アンカー"
```

cut 数が少ない場合でも、この 5 段階のどれを省略しているかを明示する。
`high` / `critical` scene で pressure と reaction が無い場合は、観客が感情変化を体験する前に話だけが進みやすいため blocking finding とする。

### 3.3 シーン間の連続性

```yaml
scene_continuity:
  # フレーム間チェーニング設計
  chaining_points:
    - from_scene: 1
      to_scene: 2
      connection_type: "visual | audio | narrative"
      technique: |
        Scene 1の最終フレームとScene 2の開始フレームで
        同じ色調・照明を維持。主人公の視線方向を揃える。

  # オーディオ連続性
  audio_continuity:
    bgm_strategy: "continuous | per_scene | transition_based"
    narration_flow: "各シーンのナレーションが自然に繋がる"
```

---

### 3.4 シーン目的（G.O.D.D.）チェック

各シーンが「物語と人物を前進させる」ための必須要素を定義する。

```yaml
scene_goal_check:
  goal: "シーン内で主人公が達成したいこと"
  obstacle: "外的/内的の障害"
  dilemma: "簡単に選べない選択肢の葛藤"
  decision: "主人公が下す決断（次シーンへ影響）"

  # すべて埋まらない場合はシーンを再設計
  all_fields_required: true
```

### 3.5 シーンのミニ構造（ビート設計）

シーンは小さな物語として、内部で変化（value shift）を起こす。

```yaml
scene_micro_structure:
  beats:
    - "Establish the scene"  # 状況の提示
    - "Catalyst"             # 触発・変化の兆し
    - "Rising action"        # 圧力の上昇
    - "Climax"               # 反応・決定の瞬間
    - "Aftermath"            # 余韻・次への布石

  value_shift_required: true
```

### 3.6 Show, don’t tell を担保するチェック

情報伝達はセリフよりも行動・視覚・サブテキストを優先する。

```yaml
show_dont_tell_check:
  replace_exposition_with_visual: true
  replace_exposition_with_action: true
  lines_without_visual_support: 0  # 説明セリフの残数
```

### 3.7 script breakdown / shot list / storyboard との接続

台本は制作工程に接続される前提で設計する。

```yaml
previsualization_handoff:
  script_breakdown:
    extracted_elements:
      - cast
      - wardrobe
      - props
      - sfx
      - locations

  shot_list:
    required_fields:
      - shot_type
      - camera_angle
      - camera_movement
      - lighting

  storyboard:
    required_fields:
      - key_frame
      - composition
      - motion_direction
```

## 第4章：タイムライン設計

### 4.1 時間配分計算

動画の長さに応じた自動計算：

```yaml
timeline_calculation:
  total_duration: 60  # 秒

  # ヒーローズジャーニー配分（参考）
  #
  # 注意:
  # - これは“当てはめる公式”ではなく、配分の例。
  # - 物語の強みが別の構造にある場合は、スコア（視聴維持/感情/映像化/一貫性）が高くなる配分を優先する。
  phase_allocation:
    ordinary_world:
      percent: 10
      seconds: 6
    call_to_adventure:
      percent: 10
      seconds: 6
    ordeal:
      percent: 40
      seconds: 24
    transformation:
      percent: 25
      seconds: 15
    return:
      percent: 15
      seconds: 9

  # シーン配分
  scene_breakdown:
    - scene_id: 1
      phase: "ordinary_world"
      start: "00:00"
      end: "00:06"
      duration: 6
    - scene_id: 2
      phase: "call_to_adventure"
      start: "00:06"
      end: "00:12"
      duration: 6
    # ... 以下続く
```

### 4.2 ペーシングガイドライン

```yaml
pacing_guidelines:
  # ナレーション速度
  narration:
    japanese_wps: 4  # 1秒あたりの文字数（日本語）
    english_wps: 3   # 1秒あたりの単語数（英語）

  # カット変更頻度
  cuts:
    minimum_shot_duration: 2  # 最短ショット秒数
    average_shot_duration: 4  # 平均ショット秒数
    maximum_shot_duration: 8  # 最長ショット秒数

  # 感情ピーク配置
  emotional_peaks:
    first_peak: 25   # 25%地点
    second_peak: 50  # 50%地点
    climax: 75       # 75%地点
    resolution: 90   # 90%地点

  # テキスト表示時間
  text_overlay:
    minimum_display: 2  # 最短表示秒数
    characters_per_second: 8  # 1秒あたりの読める文字数
```

### 4.2.1 Affect Coordinate Layer

`6 arcs` や `emotional_peaks` は作品全体の大波形を扱う。
台本ではさらに、scene ごとに「今どの感情座標を狙うか」を持てるようにする。

原則:

- `emotional_target`
  - 人間が読みやすいラベル
- `affect.intended`
  - 比較可能な座標
- script で正本にするのは `intended` のみ
- 1 scene に複数の感情が混ざる場合は、scene に baseline を置き、必要な cut だけ override する

推奨レンジ:

- `valence`: `-1.0 .. 1.0`
- `arousal`: `0.0 .. 1.0`

使い方:

- opening
  - `curiosity` / `unease` / `awe` を早く立てる
- middle
  - `bond` と `strain` を交互に使い、ずっと高 arousal にしない
- climax
  - arousal を高くし、valence は ending mode に応じて決める
- ending
  - 多くの場合、最終印象は valence より arousal の落とし方で決まる

```yaml
affect:
  intended:
    valence: -0.4
    arousal: 0.8
    label_hint: "dread"
    audience_job: "strain"
    contrast_from_previous: "spike"
```

### 4.3 タイムラインビジュアライゼーション

```
00:00 ────────────────────────────────────── 01:00
  │                                           │
  ├─ VIDEO ───────────────────────────────────┤
  │ [S1]  [S2]  [S3]  [S4]  [S5]  [S6] [S7][S8]
  │  6s    6s    8s    8s    8s    9s   6s  9s │
  │                                           │
  ├─ EMOTIONAL ARC ───────────────────────────┤
  │   ↗     ↗↘    ↗↗    ★Peak   ↘↗   ↘      │
  │                                           │
  ├─ NARRATION ───────────────────────────────┤
  │ "..."  "..."  "..." "..." "..." "..." ... │
  │                                           │
  ├─ BGM ─────────────────────────────────────┤
  │ ♪ intro ─── ♪ build ─── ♪ climax ♪ end   │
  │                                           │
  └───────────────────────────────────────────┘
```

---

## 第5章：台本生成プロセス

### 5.1 入力から台本への変換フロー

```
1. 物語スクリプト読み込み
   └→ output/stories/{topic}_{timestamp}.md

1.5. Goal / Success / Scope 確認
   ├→ viewer takeaway / must_cover / reveal_constraints を確認
   ├→ fact / creative boundary と ask-before-edit 条件を確認
   └→ 変更禁止 scope があれば先に固定

2. キャラクター抽出
   ├→ protagonist情報の抽出
   ├→ ペルソナ詳細の設計
   └→ 固定プロンプトの作成

3. シーン分解
   ├→ 物語構造からシーン数を決定
   ├→ 各シーンの時間配分
   └→ 感情曲線のマッピング

4. 詳細記述
   ├→ 各シーンの視覚指示
   ├→ 各シーンの音声指示
   └→ トランジション設計

5. 品質チェック
   ├→ 一貫性検証
   ├→ 制作可能性検証
   └→ 時間配分検証

6. 出力
   └→ output/scripts/{topic}_{timestamp}.md
```

### 5.2 物語パターン別のシーン構成

#### パターン1: 隠された真実型

```yaml
scene_structure:
  - scene: 1
    purpose: "常識・通説の提示"
    visual: "典型的・見慣れた光景"

  - scene: 2
    purpose: "疑問の提起"
    visual: "違和感を示す要素"

  - scene: 3-5
    purpose: "真実の段階的開示"
    visual: "証拠・データ・歴史的映像"

  - scene: 6-7
    purpose: "真実の全体像"
    visual: "Before/Afterの対比"

  - scene: 8
    purpose: "新しい理解"
    visual: "パラダイムシフトの象徴"
```

#### パターン2: 英雄譚型

```yaml
scene_structure:
  - scene: 1
    purpose: "英雄の日常・出発前"
    visual: "普通の環境での主人公"

  - scene: 2
    purpose: "冒険への召命"
    visual: "転機となる出来事"

  - scene: 3-5
    purpose: "試練と成長"
    visual: "困難に立ち向かう姿"

  - scene: 6-7
    purpose: "最大の試練と勝利"
    visual: "クライマックスの瞬間"

  - scene: 8
    purpose: "変容した姿での帰還"
    visual: "成長を示す対比映像"
```

### 5.3 自動計算ロジック

```python
# 時間配分の自動計算（概念）
def calculate_scene_timing(total_duration, num_scenes, emotional_arc):
    """
    total_duration: 動画の総尺（秒）
    num_scenes: シーン数
    emotional_arc: 感情曲線タイプ
    """
    # ヒーローズジャーニー配分（参考。物語に合わせて最適化する）
    phases = {
      'ordinary_world': 0.10,
      'call_to_adventure': 0.10,
      'ordeal': 0.40,
      'transformation': 0.25,
        'return': 0.15
    }

    # 感情ピークに基づく調整
    if emotional_arc == 'man_in_hole':
        phases['ordeal'] += 0.05
        phases['transformation'] -= 0.05

    return {phase: int(total_duration * ratio)
            for phase, ratio in phases.items()}
```

---

## 第6章：品質検証

### 6.1 一貫性チェック

```yaml
consistency_check:
  visual:
    - character_appearance_consistent: true/false
    - color_palette_consistent: true/false
    - lighting_style_consistent: true/false
    - aspect_ratio_consistent: true/false

  audio:
    - narration_voice_consistent: true/false
    - bgm_mood_appropriate: true/false
    - volume_levels_balanced: true/false

  narrative:
    - story_arc_complete: true/false
    - character_transformation_visible: true/false
    - emotional_beats_placed: true/false
```

### 6.2 制作可能性チェック

```yaml
feasibility_check:
  technical:
    - all_prompts_generatable: true/false
    - timing_realistic: true/false
    - transitions_defined: true/false

  resource:
    - character_references_available: true/false
    - style_references_available: true/false
    - audio_assets_identified: true/false
```

### 6.3 時間配分チェック

```yaml
timing_check:
  narration:
    - text_fits_duration: true/false
    - reading_speed_natural: true/false

  visual:
    - minimum_shot_duration_met: true/false
    - no_rushed_transitions: true/false

  overall:
    - total_matches_target: true/false
    - pacing_appropriate: true/false
```

---

## 第7章：出力スキーマ（完全版）

```yaml
# ============================================================
# 台本ファイル: output/scripts/{topic}_{timestamp}.md
# ============================================================

# === メタ情報 ===
script_metadata:
  topic: "string"
  source_story: "output/stories/{file}.md"
  source_visual_value: "output/<topic>_<timestamp>/visual_value.md"
  created_at: "ISO8601"
  target_duration: 60  # 秒
  aspect_ratio: "9:16"
  resolution: "1080x1920"
  story_pattern: "hidden_truth | counterintuitive | mystery | hero | emotional"

# === キャラクター設計 ===
characters:
  - character_id: "protagonist"
    name: "string"
    role: "主人公"

    narrative_function:
      ordinary_world: "string"
      desire: "string"
      flaw: "string"
      transformation: "string"

    visual_identity:
      face:
        shape: "oval"
        eyes: "dark brown, almond-shaped"
        hair: "short black, slight wave"
        distinguishing_features: "small mole on left cheek"
      body:
        height: "medium"
        build: "slim"
        posture: "slightly forward-leaning"
      default_outfit:
        top: "navy blue hoodie over white t-shirt"
        bottom: "dark blue jeans"
        footwear: "white sneakers"
        accessories: "silver watch on left wrist"

    fixed_prompts:
      face: "oval face with dark brown almond-shaped eyes, short black hair with slight wave, small mole on left cheek"
      body: "medium height, slim build, slightly forward-leaning posture"
      outfit: "navy blue hoodie over white t-shirt, dark blue jeans, white sneakers, silver watch"
      style: "realistic, cinematic, warm color grading"

    reference_images:
      - path: "assets/characters/protagonist_front.png"
      - path: "assets/characters/protagonist_side.png"

    voice:
      tone: "落ち着いた、知的"
      tts_voice_id: "elevenlabs_adam"

# === スタイルガイド ===
style_guide:
  visual_style: "cinematic, warm color grading, shallow depth of field"
  color_palette:
    primary: "#2C3E50"
    secondary: "#E74C3C"
    accent: "#F39C12"
  lighting: "soft natural lighting, golden hour preference"
  forbidden:
    - "cartoon style"
    - "anime"
    - "watercolor"

# === タイムライン ===
timeline:
  total_duration: 60
  phase_allocation:
    ordinary_world: { percent: 10, seconds: 6, scenes: [1] }
    call_to_adventure: { percent: 10, seconds: 6, scenes: [2] }
    ordeal: { percent: 40, seconds: 24, scenes: [3, 4, 5] }
    transformation: { percent: 25, seconds: 15, scenes: [6, 7] }
    return: { percent: 15, seconds: 9, scenes: [8] }

# === シーン詳細 ===
scenes:
  - scene_id: 1
    scene_name: "オープニング - フック"
    timing:
      position_percent: "0-10"
      duration_seconds: 6
      timestamp: "00:00-00:06"

    narrative:
      phase: "ordinary_world"
      purpose: "視聴者の注意を引く問いかけ"
      hook_type: "question"
      emotional_target: "curiosity"

    affect:
      intended:
        valence: 0.2
        arousal: 0.65
        label_hint: "curiosity"
        audience_job: "hook"
        contrast_from_previous: "lift"

    visual_value:
      source_part_id: ""
      role: "none"
      narration_policy: "spoken"
      placement_guard: ""

    characters:
      - character_id: "protagonist"
        action: "窓の外を見つめている"
        expression: "thoughtful, slightly troubled"
        position: "center"

    visual:
      location:
        setting: "modern apartment living room"
        time_of_day: "morning"
        weather: "sunny, light streaming through windows"
        props: ["coffee mug", "laptop on table", "plants"]

      shot:
        type: "medium"
        angle: "eye_level"
        movement: "slow_zoom_in"
        duration: 6

      composition:
        rule_of_thirds: "subject on left third"
        depth: "plants in foreground, subject in middle, window in background"
        lighting: "soft natural light from right"

      p600_image_handoff:
        visual_thesis: "朝の室内で、主人公が日常の中に違和感を覚え始める一枚絵"
        first_frame_brief: "主人公が窓の外へ視線を向ける直前。コーヒーマグと開いたノートPCが前景にあり、朝光が横顔を照らす"
        subject_priority:
          - "主人公の横顔と視線"
          - "日常を示す前景の小道具"
          - "外の光"
        screen_evidence:
          - "観客が、主人公が何かに気づきかけていると読める"
          - "まだ行動は始まっておらず、次cutで動き出せる"
        blocking_notes: "前景に机とマグ、中景に主人公、背景に窓。視線は画面奥へ流す"
        lighting_notes: "朝の自然光。穏やかだが、少し冷たい影を残す"
        forbidden_prompt_metadata:
          - "scene_id / cut_id"
          - "物語タイトルだけでの説明"
          - "最初の1フレーム / first frame という制作メタ"

    audio:
      narration:
        text: "なぜ私たちは、当たり前だと思っていることに疑問を持たないのだろう"
        timing: "sync"
        emotion: "contemplative, slightly mysterious"
      bgm:
        track: "ambient_mystery_intro"
        mood: "mysterious"
        volume: 0.25
        fade: "fade_in"
      sfx:
        - effect: "soft morning ambience"
          timing: "00:00"
          volume: 0.2

    text_overlay:
      main_text:
        content: "なぜ私たちは疑問を持たないのか"
        position: "bottom_center"
        style: "subtitle"
        timing: "00:01-00:05"

    transition:
      to_next_scene: "dissolve"
      duration: 0.5

  # === Scene 2-8: 同様の構造で続く ===

  - scene_id: 4
    scene_name: "中盤の視覚報酬"
    timing:
      position_percent: "40-56"
      duration_seconds: 24
      timestamp: "00:24-00:48"

    narrative:
      phase: "ordeal"
      purpose: "視聴者に、この題材で最も見たいものを体験させる"
      hook_type: "visual_payoff"
      emotional_target: "awe"

    visual_value:
      source_part_id: "midroll_visual_payoff_01"
      role: "visual_payoff"
      narration_policy: "silent"
      placement_guard: "20-80%"

    # 実際の manifest / scene_conte では 4-6 cuts に分解し、
    # 各 cut を 4 秒・ナレーションなしで表現する

# === エンゲージメント設計（story-creationから継承）===
engagement_design:
  primary_hook:
    type: "question"
    content: "なぜ私たちは疑問を持たないのか"
    position_percent: 2

  tension_arc:
    - position_percent: 15
      tension_level: 3
    - position_percent: 40
      tension_level: 7
    - position_percent: 60
      tension_level: 9
    - position_percent: 90
      tension_level: 5

# === 品質チェック結果 ===
quality_check:
  consistency:
    character_appearance: true
    color_palette: true
    lighting_style: true
  feasibility:
    prompts_generatable: true
    timing_realistic: true
  timing:
    narration_fits: true
    pacing_appropriate: true

# === 制作メモ ===
production_notes:
  - "Scene 3-5の葛藤パートでは緊張感を維持するためテンポを上げる"
  - "クライマックス前（Scene 6）で一度静寂を作り、インパクトを強調"
  - "エンディングは冒頭と視覚的に呼応させる（循環構造）"
```

---

## 実行フロー

```
1. 物語スクリプト読み込み
   └→ output/stories/{topic}_{timestamp}.md

2. メタ情報設定
   ├→ 動画長さ決定
   ├→ アスペクト比設定
   └→ 物語パターン確認

3. キャラクター設計
   ├→ 物語から主人公情報抽出
   ├→ ペルソナ詳細設計
   ├→ 固定プロンプト作成
   └→ 参照画像パス定義

4. タイムライン設計
   ├→ フェーズ別時間配分計算
   ├→ シーン数決定
   └→ 各シーンの尺決定

5. シーン詳細記述
   ├→ 各シーンの視覚指示
   ├→ 各シーンの音声指示
   ├→ テキストオーバーレイ
   └→ トランジション設計

6. 品質検証
   ├→ 一貫性チェック
   ├→ 制作可能性チェック
   └→ 時間配分チェック

7. 出力
   └→ output/scripts/{topic}_{timestamp}.md
```

---

## 参考文献

### 脚本技法

- Field, Syd. *Screenplay: The Foundations of Screenwriting*. 1979.
- McKee, Robert. *Story*. 1997.
- Snyder, Blake. *Save the Cat!*. 2005.

### 映像制作

- Katz, Steven. *Film Directing Shot by Shot*. 1991.
- Block, Bruce. *The Visual Story*. 2007.

### AI生成のためのプロンプト設計

- 本書内「固定プロンプト」の運用ルールを参照

---

*最終更新: 2026-01-11*

## p420 Cut Design Upgrade v2.1

改善版では、p420 cut blueprint を `viewer-facing cinematic beat` の設計として扱う。scene から cut を作るときは、scene の `dramatic_question`、`value_shift.visible_evidence`、`causal_turn`、`reveal_constraints`、`handoff_to_next_scene` を cut 列のどこで回収するかを先に決める。

追加の正本は `docs/implementation/cut-loop.md` と `workflow/cut-blueprint-template.yaml`。

### p420 Additional Output

```yaml
scene_cut_coverage_plan:
  coverage_strategy: "reverse_from_scene_event"
  source_schema_version: "scene_event_v1"
  min_cut_count:
    by_importance: 3
    by_duration: 3
    by_event_beats: 4
    selected: 4
    exception_reason: ""
  event_beat_inventory:
    - beat_id: "scene1_event_setup"
      beat_function: "setup"
      must_be_seen: true
      assigned_cut_ids: []
  scene_obligations:
    - obligation_id: "scene_event_sequence_01"
      source: "scene_event.event_sequence"
      evidence:
        - beat_id: "scene1_event_setup"
          beat_function: "setup"
          required_visual_evidence: []
      assigned_cut_ids: []
  cut_assignments:
    - cut_index: 1
      cut_selector: ""
      obligation_ids: []
      cut_function: ""
      event_assignment:
        source_event_contract:
          primary_event_beat_id: "scene1_event_setup"
          source_event_beat_ids: ["scene1_event_setup"]
      target_beat: ""
      visual_proof: ""
      audience_knowledge_delta: ""
      causal_proof: ""
      required_roles: []
      anti_redundancy_key: ""
  unassigned_obligations: []
  overloaded_cuts: []
  duplicate_meaning_risks: []
```

各 cut は `cut_contract` を正本にする。既存 reader のために `scene_contract` は互換 alias として残してよい。

```yaml
cut_contract:
  schema_version: "3.0"
  source_event_contract:
    primary_event_beat_id: "scene1_event_setup"
    source_event_beat_ids: ["scene1_event_setup"]
    event_beat_function: "setup"
    event_time_position: "before_trigger"
    source_event_summary: ""
    source_visible_action: ""
    source_visible_reaction: ""
    no_reaction_required_reason: ""
    source_required_visual_evidence: []
    event_facts_to_preserve: []
    event_facts_not_to_invent: []
    allowed_reveal_info_ids: []
    forbidden_reveal_info_ids: []
  cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff|custom"
  intent_budget:
    primary_intent: ""
    assigned_obligation_ids: []
    overload_exception_reason: ""
  viewer_contract:
    target_beat: ""
    screen_question: ""
    dramatic_job: ""
    audience_knowledge_delta: ""
    causal_proof: ""
    visual_evidence: []
    required_roles: []
    anti_redundancy_key: ""
    emotional_micro_shift:
      from: ""
      to: ""
    mixed_affect_design:
      mode: "none|single|mixed|tension_release|bittersweet|aftertaste"
      optional: true
      apply_when: []
      positive_valence_thread: ""
      negative_valence_thread: ""
      arousal_strategy: "hold|rise|drop|spike|release"
      audience_rollercoaster_job: "none|bond|strain|release|reframe|aftertaste"
      design_intent: ""
      visible_support: []
      narration_support: []
      sound_or_rhythm_support: []
      handoff_effect: ""
      avoid_if: []
    reveal_constraints:
      inherited_from_scene: []
      allowed_reveals_in_this_cut: []
      forbidden_until_later_cut: []
      forbidden_until_later_scene: []
    visual_proof: ""
    must_show: []
    must_avoid: []
    done_when: []
  cinematic_contract: {}
  continuity_contract:
    start_state: {}
    end_state: {}
    carry_forward_to_next_cut: []
    continuity_risks: []
  cut_handoff:
    receives_from_previous: {}
    delivers_to_next: {}
  first_frame_contract:
    first_frame_brief: ""
    visible_start_state: {}
    motion_start_affordance: {}
    action_completion_state: "pre_action|early_action|mid_action|aftermath|hold"
    static_first_frame_rule: ""
    must_be_static_evidence_not_motion: true
  motion_contract:
    motion_brief: ""
    start_from_visible_state: ""
    end_state: ""
    end_frame_brief: ""
    must_not_add: []
  narration_contract:
    schema_version: "narration_contract_v2"
    story_role:
      narrative_position: "opening|middle|ending"
      cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
      voice_function: "information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence"
      audience_state_before: ""
      audience_state_after: ""
      must_cover: []
      must_not_reveal: []
      done_when: []
    visual_distance:
      distance_policy: "stay_close|contextual|meaning_first|silent"
      visible_facts_in_frame: []
      narration_should_add: []
      must_not_caption_visible_action: true
      visual_overlap_allowed: false
      visual_overlap_reason: ""
    rhythm_and_timing:
      target_speech_seconds: 0
      start_timing: "immediate|after_visual_read|mid_cut|late_cut|none"
      end_timing: "before_cut_end|on_cut_end|after_visual_resolution|none"
      pause_intent: []
    tts_readiness:
      pronunciation_targets: []
      max_sentence_chars: 42
    # compatibility aliases for older readers
    role: "setup|fact|emotion|contrast|aftertaste|silent"
    target_function: "derive_from_story_role_voice_function"
    must_cover:
      - "derive_from_story_role_must_cover"
    must_avoid:
      - "映像のキャプション化"
    done_when:
      - "derive_from_story_role_done_when"
    silence_reason: ""
  rhythm_contract:
    expected_duration_seconds: 8
    pacing: "quick|standard|slow_hold|spectacle_hold"
    comprehension_moment: ""
    cut_out_reason: ""
    audio_visual_sync_point: ""
    duration_exception:
      allowed: false
      reason: ""
  asset_dependency:
    character_ids_required: []
    object_ids_required: []
    location_ids_required: []
    variant_ids_required: []
    new_asset_requests: []
    reusable_anchor_ids: []
  downstream_handoff:
    p500_asset:
      required_asset_ids: []
      asset_candidates: []
      continuity_anchor_needed: false
      new_asset_needed: false
      reuse_allowed: false
    p600_image:
      prompt_requirements: []
      reference_requirements: []
      first_frame_must_include: []
      first_frame_must_avoid: []
    p700_narration:
      narration_requirements: []
      narrative_position: "opening|middle|ending"
      cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
      voice_function: "information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence"
      visual_distance_policy: "stay_close|contextual|meaning_first|silent"
      pronunciation_targets: []
      role: "setup|fact|emotion|contrast|aftertaste|silent"
      must_not_caption_visible_content: true
    p800_video:
      motion_requirements: []
      start_state: ""
      last_frame_or_end_state: ""
      must_not_add: []
```

### Cut Count and Split Rules

- low scene: 2 cuts 以上。
- medium scene: 3 cuts 以上。
- high scene: 5 cuts 以上。
- critical scene: 7 cuts 以上。
- さらに `ceil(target_duration_seconds / 8)` を下回らない。
- 1 cut が 12 秒を超える場合は、意図的な hold / silence / spectacle である理由を残す。
- spectacle / transformation / emotional reversal / proof reveal は `approach -> mechanism -> threshold -> reveal/payoff -> reaction -> handoff` に分ける。
- mixed affect は全 cut 必須ではない。必要な pressure / turn / payoff / reaction / terminal cut だけ `mixed_affect_design.mode != none` にし、視覚・語り・音/リズム・handoff の支えを少なくとも 1 つ示す。

### Blocking Conditions

- `target_beat` が scene summary になっている。
- `screen_question` がない。
- `visual_proof` がない。
- `first_frame_brief` が行為完了後の説明絵になっている。
- `motion_brief` が別 scene の出来事を始めている。
- narration が映像のキャプションになっている。
- turn の前に threshold がない。
- turn / payoff の後に reaction がない。
- 最終 cut が次 cut / 次 scene への handoff を持たない。
- `mixed_affect_design.mode != none` なのに支えが抽象的、または primary intent を二重化している。
