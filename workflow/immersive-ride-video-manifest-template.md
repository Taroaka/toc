# 没入型ライド: 動画マニフェストテンプレ（run root）

このテンプレは `/toc-immersive-ride` の `output/<topic>_<timestamp>/video_manifest.md` 用。

```yaml
manifest_phase: skeleton
video_metadata:
  topic: "<topic>"
  source_story: "output/<topic>_<timestamp>/story.md"
  created_at: "<ISO8601>"
  duration_seconds: 0   # ナレーション生成後に埋める（任意）
  experience: "cinematic_story"
  aspect_ratio: "16:9"
  resolution: "1280x720"
  frame_rate: 24

assets:
  character_bible:
    # 登場人物（例）。ガイドは音声（ナレーション）のみで、画面内には出さない。
    # reference_images / output の識別子は、人間が読める安定名にする（例: protagonist_front_ref / protagonist_side_ref / protagonist_back_ref）。
    - character_id: "protagonist"
      reference_images:
        - "assets/characters/protagonist_front.png"
      review_aliases: ["主人公"]   # story/script review 用の別名。日本語固有名や略称を入れる
      physical_scale:
        height_cm: 175
        silhouette_notes:
          - "成人の自然な体格。頭身と手足の長さは実写で無理がない"
      relative_scale_rules:
        - "他キャラクターと同フレームにいるときも、主人公の体格を scene 間で変えない"
      reference_variants:
        - variant_id: "protagonist_wet_ref"
          reference_images:
            - "assets/characters/protagonist_wet_front.png"
          fixed_prompts:
            - "衣装が濡れ、裾に水滴が残る"
      fixed_prompts:
        - "主人公は参照画像と完全一致（顔、髪型、服装が同一）"
        - "人間の主人公は美男美女（映画俳優レベルの魅力）。顔立ちのバランス、肌の質感、表情、目の印象が自然で実写的"
      notes: "全身ターンアラウンドの参照画像を先に生成し、主人公が映るsceneでは必ず参照する。"

  style_guide:
    visual_style: "実写、シネマティック、プラクティカルエフェクト（特撮/実物セット感）"
    forbidden:
      - "アニメ調"
      - "漫画調"
      - "イラスト調"
      - "絵"
      - "画面内テキスト"
      - "字幕"
      - "ウォーターマーク"
      - "ロゴ"
    reference_images: []

  # 舞台装置/主役級アイテム bible（任意だが強く推奨）
  # 重要要素は “キャラ同様に” 設計→参照画像→scene参照の順で固める。
  object_bible: []
  # - object_id: "tbd_setpiece"
  #   kind: "setpiece"  # setpiece|artifact|phenomenon
  #   reference_images:
  #     - "assets/objects/tbd_setpiece.png"
  #   reference_variants:
  #     - variant_id: "tbd_setpiece_activated"
  #       reference_images:
  #         - "assets/objects/tbd_setpiece_activated.png"
  #       fixed_prompts:
  #         - "発光状態/起動状態の差分"
  #   fixed_prompts:
  #     - "材質/構造の不変条件（実写で成立する重量感/工芸/経年）"
  #     - "機構/ルール/誘惑/ショー性（物語に無関係でも映像として魅力的に）"
  #     - "文字で説明しない（看板/刻印/銘板なし）。形/光/動きで伝える"
  #   cinematic:
  #     role: "映画での役割（物語/感情/テーマ）"
  #     visual_takeaways:
  #       - "映像から観客に与える情報（文字なしで理解できる形にする）"
  #     spectacle_details:
  #       - "見せ場ディテール（隠し部屋、可動構造、ショー等。メイン筋と無関係でもOK）"
  #   notes: null

scenes:
  # 0) キャラクター参照（推奨）
  # `scripts/toc-immersive-ride-generate.sh` で、正面出力から側面/背面と結合stripを自動生成する。
  - scene_id: 0
    reference_id: "protagonist_front_ref"
    kind: character_reference
    image_generation:
      # reference scene は continuity anchor を作るためのもの。毎sceneではない。
      # review metadata は image_generation.review 側で持つ。
      # contract:
      #   target_focus: "character"
      #   must_include: []
      #   must_avoid: []
      #   done_when: []
      # review:
      #   agent_review_ok: true
      #   agent_review_reason_keys: []
      #   agent_review_reason_messages: []
      #   rubric_scores: {}
      #   overall_score: 0.0
      #   human_review_ok: false
      #   human_review_reason: ""
      # subagent は不足 entry を false にし、reason key を残し、fix 後に true へ戻す。
      # human override は human_review_ok / human_review_reason に記録する。
      # required block:
      # [全体 / 不変条件] / [登場人物] / [小道具 / 舞台装置] / [シーン] / [連続性] / [禁止]
      # 1 つでも欠けていれば subagent review は false にする。
      tool: "google_nanobanana_2"
      character_ids: ["protagonist"]
      character_variant_ids: []  # Optional: ["protagonist_wet_ref"] のように、そのscene専用のvariantを選ぶ
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        実写、シネマティック、プラクティカルエフェクト（実物セット感）。自然な映画照明。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [シーン]
        主人公のターンアラウンド参照画像（全身専用）。
        全身（頭からつま先まで）を入れ、足先が切れない（クロップしない）。ニュートラルな姿勢で中央構図。
        顔寄り、上半身のみ、途中クロップは不可。
        背景はクリーンで無地。

        [禁止]
        アニメ/漫画/イラスト調。あらゆる文字要素。
      output: "assets/characters/protagonist_front.png"  # readable reference id: protagonist_front_ref
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null

  # 1) scene静止画 + つなぎ動画（ガイドは音声のみ）
  # 推奨: story scene は 10刻みで生成する（10,20,30...）。character_reference scene は別枠。
  - scene_id: 10
    timestamp: "00:00-00:08"
    image_generation:
      # 新規の静止画は、場所/物体/人物状態の continuity anchor が必要な scene で優先する。
      # 既存の anchor frame を再利用できる cut は、新規生成を強制しない。
      # review metadata は image_generation.review 側で持つ:
      # contract:
      #   target_focus: "character"
      #   must_include: []
      #   must_avoid: []
      #   done_when: []
      # review:
      #   agent_review_ok: true
      #   agent_review_reason_keys: []
      #   agent_review_reason_messages: []
      #   rubric_scores: {}
      #   overall_score: 0.0
      #   human_review_ok: false
      #   human_review_reason: ""
      # required block:
      # [全体 / 不変条件] / [登場人物] / [小道具 / 舞台装置] / [シーン] / [連続性] / [禁止]
      tool: "google_nanobanana_2"
      character_ids: ["protagonist"]
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        実写、シネマティック、プラクティカルエフェクト（実物セット感）。自然な映画照明。
        視点: 客観（三人称）。1カット内で視点ブレさせない。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        登場人物は参照画像と完全一致（顔、髪型、服装が同一）。

        [小道具 / 舞台装置]

        [シーン]
        舞台: <topic> の世界へ入る入口。実物セット、実写照明。
        見せ場: 最初の登場人物が前方に現れ、世界へ引き込まれる。
        構図: 主役を中景、入口/ゲートを遠景の中心に置き、導線（道/光/柱）で視線誘導する。

        [連続性]
        次への仕込み: 導線が自然につながり、照明が滑らかに遷移する。

        [禁止]
        アニメ/漫画/イラスト調。あらゆる文字要素。人体の崩れ、指の増殖、パース破綻。
      output: "assets/scenes/scene10.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null
    video_generation:
      # tool: "google_veo_3_1"  # disabled; routed to Kling for safety
      # tool: "kling_3_0"
      # tool: "kling_3_0_omni"
      # tool: "seedance"       # BytePlus ModelArk Seedance (video; see ARK_* env)
      tool: "kling_3_0"
      duration_seconds: 8
      first_frame: "assets/scenes/scene10.png"
      last_frame: "assets/scenes/scene20.png"
      motion_prompt: "カメラが滑らかに前進し、照明が自然に遷移する（1カット内で視点ブレさせない）。"
      output: "assets/scenes/scene10_to_20.mp4"
    audio:
      narration:
        contract:
          target_function: ""
          must_cover: []
          must_avoid: []
          done_when: []
        # review metadata は audio.narration.review に保持する。
        text: ""
        tts_text: ""
        tool: "elevenlabs"
        output: "assets/audio/scene10_narration.mp3"
        normalize_to_scene_duration: false

  - scene_id: 20
    timestamp: "00:08-00:16"
    image_generation:
      # 同上: ここでは新規生成を前提にしない。必要なときだけ anchor を更新する。
      tool: "google_nanobanana_2"
      character_ids: ["protagonist"]
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        実写、シネマティック、プラクティカルエフェクト（実物セット感）。自然な映画照明。
        視点: 客観（三人称）。1カット内で視点ブレさせない。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        登場人物は参照画像と完全一致。

        [小道具 / 舞台装置]

        [シーン]
        舞台: <topic> の世界をさらに進む。実物の霧と軽い水しぶき（プラクティカル）。
        見せ場: 前方の出来事に登場人物が反応する。
        構図: 中景の登場人物と、遠景の出来事/発見を同一フレームに入れる。導線で前進感を作る。

        [連続性]
        前と一致: 照明方向、色温度、空気感。
        次への仕込み: 緩やかな左カーブが始まり、次の発見を予告する。

        [禁止]
        アニメ/漫画/イラスト調。あらゆる文字要素。人体の崩れ、指の増殖、パース破綻。
      output: "assets/scenes/scene20.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null
    video_generation:
      # tool: "google_veo_3_1"  # disabled; routed to Kling for safety
      # tool: "kling_3_0"
      # tool: "kling_3_0_omni"
      # tool: "seedance"       # BytePlus ModelArk Seedance (video; see ARK_* env)
      tool: "kling_3_0"
      duration_seconds: 8
      first_frame: "assets/scenes/scene20.png"
      last_frame: "assets/scenes/scene30.png"
      motion_prompt: "緩やかなカーブを描きながら前進を継続。カメラ高さと地平線の安定を保つ。"
      output: "assets/scenes/scene20_to_30.mp4"
    audio:
      narration:
        contract:
          target_function: ""
          must_cover: []
          must_avoid: []
          done_when: []
        # review metadata は audio.narration.review に保持する。
        text: ""
        tool: "elevenlabs"
        output: "assets/audio/scene20_narration.mp3"
        normalize_to_scene_duration: false

  - scene_id: 30
    timestamp: "00:16-00:24"
    image_generation:
      # 同上
      tool: "google_nanobanana_2"
      character_ids: ["protagonist"]
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        実写、シネマティック、プラクティカルエフェクト（実物セット感）。自然な映画照明。
        視点: 客観（三人称）。1カット内で視点ブレさせない。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        登場人物は参照画像と完全一致し、はっきり見える。

        [小道具 / 舞台装置]

        [シーン]
        舞台: <topic> のクライマックス的な“発見”エリア（実物セット + 映画照明）。
        見せ場: 遠景の発見が画面を満たし、登場人物が反応する。
        構図: 登場人物が中景、発見が遠景。導線/光で中心へ視線誘導。

        [連続性]
        前と一致: 照明方向と前進の段取り。

        [禁止]
        アニメ/漫画/イラスト調。あらゆる文字要素。人体の崩れ、指の増殖、パース破綻。
      output: "assets/scenes/scene30.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null

  # Example B-roll（物語キャラクター非表示でも、スタイル/連続性は維持）
  - scene_id: 40
    timestamp: "00:24-00:32"
    image_generation:
      # B-roll でも新規静止画は必須ではない。連続性が保てるなら anchor を再利用する。
      tool: "google_nanobanana_2"
      character_ids: []
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        実写、シネマティック、プラクティカルエフェクト（実物セット感）。自然な映画照明。
        視点: 客観（三人称）。1カット内で視点ブレさせない。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [小道具 / 舞台装置]

        [シーン]
        B-roll: <topic> 世界の環境だけを見せる（登場人物は映らない）。実物セット + 映画照明。

        [禁止]
        アニメ/漫画/イラスト調。あらゆる文字要素。
      output: "assets/scenes/scene40.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null
```
