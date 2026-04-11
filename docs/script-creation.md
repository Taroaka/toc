# Script Creation System

台本作成システム - 物語を動画制作用の具体的な台本に変換する手順書

## 概要

このドキュメントは、`docs/story-creation.md` で設計した物語を、`docs/video-generation.md` の技術仕様に適合する具体的な台本に変換するための手順を定義する。

### 位置づけ

```
[情報収集] → [物語生成] → [視覚価値設計] → [台本作成] → [動画生成]
                                          ↑ 本書
```

### 入力

- `output/stories/{topic}_{timestamp}.md` - 物語スクリプト（story-creation.md出力）
- `output/<topic>_<timestamp>/visual_value.md` - 中盤の視覚報酬パート設計（あれば参照）
- 物語構造、感情曲線、エンゲージメント設計
- `docs/affect-design.md` - Russell 系の valence / arousal 補助レイヤー
- `docs/video-generation.md` - 汎用の動画生成原則
- `workflow/playbooks/video-generation/kling.md` - `kling_3_0` / `kling_3_0_omni` 利用時の専用 prompt guide

### 出力

- `output/scripts/{topic}_{timestamp}.md` - 制作用台本
- キャラクター設計、シーン詳細、タイムライン

---

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
**中盤の視覚報酬** として script に取り込む。

基本ルール:

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

現行 ElevenLabs 運用では、manifest へ同期する値は `tts_text` 系の spoken form を優先し、`audio.narration.text` と `audio.narration.tts_text` の両方へ反映する。

cut ごとに少なくとも次を持てる。

```yaml
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

- `narration`
  - 作品として読ませる台本文面
- `tts_text`
  - 読み上げ用 spoken form
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

人間 review の観点は固定しておく。

- 昔話 / 作品文脈として自然か
- reveal 順序を壊していないか
- ひらがな読みで違和感がないか
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
  - `tts_text`
  - 人レビューで来た image/video 指示
- `script.md` が持ちすぎないもの
  - provider 固有 prompt 文法
  - 実行パラメータ
  - 依存解決済みの asset wiring 全体

原則:

- `script.md` は image/video をまったく語らない文書にはしない
- ただし、image/video の **生成方法そのもの** を主責務にしない
- `tts_text` は TTS 専用の spoken form であり、image/video generation の主ソースにしない

したがって、`script.md` は「何を見せるか」「何をまだ見せてはいけないか」「人レビューでどの参照画像や演出意図が入ったか」を保持し、`video_manifest.md` がそれを prompt / asset / motion / continuity へ materialize する。

ただし reusable asset の設計は cut stage より前に独立して扱ってよい。asset に関する human request は、まず `asset_plan.md` に集約し、その review / approve 後に asset を生成し、cut stage がそれを参照する。

### 1.7 Narration Distance Policy

`narration` と `visual_beat` は、常に差を作るのでも、常に一致させるのでもなく、**scene の役割**で距離を決める。

基本方針:

- 序盤 / 中盤
  - 視聴者を物語の中へ入れることを優先
  - `narration` は `visual_beat` に基本的に沿ってよい
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

      # AI生成用プロンプト（完成形）
      generation_prompt: |
        [主題] + [スタイル] + [環境] + [照明] + [カメラ]
        例: "A young woman with oval face and short black hair,
        wearing navy blue hoodie, standing in a modern apartment,
        morning sunlight streaming through windows, medium shot,
        looking thoughtfully out the window"

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

      generation_prompt: |
        A young person with oval face and dark brown eyes, short black hair,
        wearing navy blue hoodie over white t-shirt,
        standing in a modern apartment living room,
        morning sunlight streaming through large windows,
        medium shot, looking thoughtfully out the window,
        cinematic, warm color grading, shallow depth of field

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
