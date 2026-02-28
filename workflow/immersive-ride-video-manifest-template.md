# 没入型ライド: 動画マニフェストテンプレ（run root）

このテンプレは `/toc-immersive-ride` の `output/<topic>_<timestamp>/video_manifest.md` 用。

```yaml
video_metadata:
  topic: "<topic>"
  source_story: "output/<topic>_<timestamp>/story.md"
  created_at: "<ISO8601>"
  duration_seconds: 0   # filled after narration is generated (optional)
  experience: "ride_action_boat"
  aspect_ratio: "16:9"
  resolution: "1280x720"
  frame_rate: 24

assets:
  character_bible:
    # 登場人物（例）。ガイドは音声（ナレーション）のみで、画面内には出さない。
    - character_id: "protagonist"
      reference_images:
        - "assets/characters/protagonist_front.png"
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
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["protagonist"]
      object_ids: []
      prompt: |
        [全体 / 不変条件]
        実写、シネマティック、プラクティカルエフェクト（実物セット感）。自然な映画照明。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [シーン]
        主人公のターンアラウンド参照画像。
        全身（頭からつま先まで）を入れ、足先が切れない（クロップしない）。ニュートラルな姿勢で中央構図。
        背景はクリーンで無地。

        [禁止]
        アニメ/漫画/イラスト調。あらゆる文字要素。
      output: "assets/characters/protagonist_front.png"
      aspect_ratio: "16:9"
      image_size: "2K"
      references: []
      iterations: 4
      selected: null

  # 1) scene静止画 + つなぎ動画（ガイドは音声のみ）
  # 推奨: scene_id を10刻みにする（後で差し込みやすい）。
  - scene_id: 10
    timestamp: "00:00-00:08"
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["protagonist"]
      object_ids: []
      prompt: |
        [全体 / 不変条件]
        一人称POVのライド（アクションボート）。手は画面下の前景に必ず入れ、安全バーを握っている。
        テーマパークのライド軌道（中央レール）が中央に見える。実写、シネマティック、実物セット感。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        登場人物は参照画像と完全一致（顔、髪型、服装が同一）。

        [小道具 / 舞台装置]

        [シーン]
        舞台: <topic> の世界へ入る入口。実物セット、実写照明。
        見せ場: 最初の登場人物が前方に現れ、世界へ引き込まれる。
        構図: 手+安全バーが前景、軌道は中央、登場人物は中景、目的地は遠景。

        [連続性]
        次への仕込み: 軌道が自然につながり、照明が滑らかに遷移する。

        [禁止]
        アニメ/漫画/イラスト調。手の崩れ、指の増殖。あらゆる文字要素。
      output: "assets/scenes/scene10.png"
      aspect_ratio: "16:9"
      image_size: "2K"
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
      motion_prompt: "Ride action boat moves forward smoothly along the track; natural lighting transition."
      output: "assets/scenes/scene10_to_20.mp4"
    audio:
      narration:
        text: "TODO: このクリップのナレーション（1カット=1ナレーション、15秒以内目安）"
        tool: "elevenlabs"
        output: "assets/audio/scene10_narration.mp3"
        normalize_to_scene_duration: false

  - scene_id: 20
    timestamp: "00:08-00:16"
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["protagonist"]
      object_ids: []
      prompt: |
        [全体 / 不変条件]
        一人称POVのライド（アクションボート）。手は画面下の前景に必ず入れ、安全バーを握っている。
        テーマパークのライド軌道（中央レール）が中央に見える。実写、シネマティック、実物セット感。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        登場人物は参照画像と完全一致。

        [小道具 / 舞台装置]

        [シーン]
        舞台: <topic> の世界をさらに進む。実物の霧と軽い水しぶき（プラクティカル）。
        見せ場: 前方の出来事に登場人物が反応する。
        構図: 登場人物は中景、出来事/発見は遠景、軌道は中央を維持。

        [連続性]
        前と一致: 手と安全バーのディテール、前進方向。
        次への仕込み: 緩やかな左カーブが始まり、次の発見を予告する。

        [禁止]
        アニメ/漫画/イラスト調。手の崩れ、指の増殖。あらゆる文字要素。
      output: "assets/scenes/scene20.png"
      aspect_ratio: "16:9"
      image_size: "2K"
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
      motion_prompt: "緩やかなカーブを描きながら前進を継続。POVと手と安全バーの位置を維持。"
      output: "assets/scenes/scene20_to_30.mp4"
    audio:
      narration:
        text: "TODO: このクリップのナレーション（1カット=1ナレーション、15秒以内目安）"
        tool: "elevenlabs"
        output: "assets/audio/scene20_narration.mp3"
        normalize_to_scene_duration: false

  - scene_id: 30
    timestamp: "00:16-00:24"
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: ["protagonist"]
      object_ids: []
      prompt: |
        [全体 / 不変条件]
        一人称POVのライド（アクションボート）。手は画面下の前景に必ず入れ、安全バーを握っている。
        ライド軌道（中央レール）は中央。実写、シネマティック、実物セット感。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        登場人物は参照画像と完全一致し、はっきり見える。

        [小道具 / 舞台装置]

        [シーン]
        舞台: <topic> のクライマックス的な“発見”エリア（実物セット + 映画照明）。
        見せ場: 遠景の発見が画面を満たし、登場人物が反応する。
        構図: 手+安全バーが前景、登場人物が中景、発見が遠景、軌道は中央。

        [連続性]
        前と一致: 照明方向と前進の段取り。

        [禁止]
        アニメ/漫画/イラスト調。手の崩れ、指の増殖。あらゆる文字要素。
      output: "assets/scenes/scene30.png"
      aspect_ratio: "16:9"
      image_size: "2K"
      references: []
      iterations: 4
      selected: null

  # Example B-roll (no story character visible; still must keep POV invariants)
  - scene_id: 40
    timestamp: "00:24-00:32"
    image_generation:
      tool: "google_nanobanana_pro"
      character_ids: []
      object_ids: []
      prompt: |
        [全体 / 不変条件]
        一人称POVのライド（アクションボート）。手は画面下の前景に必ず入れ、安全バーを握っている。
        ライド軌道（中央レール）は中央。実写、シネマティック、実物セット感。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [小道具 / 舞台装置]

        [シーン]
        B-roll: <topic> 世界の環境だけを見せる（登場人物は映らない）。実物セット + 映画照明。

        [禁止]
        アニメ/漫画/イラスト調。あらゆる文字要素。
      output: "assets/scenes/scene40.png"
      aspect_ratio: "16:9"
      image_size: "2K"
      references: []
      iterations: 4
      selected: null
```
