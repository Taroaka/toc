# 没入型: 雲上の島を歩く体験（cloud_island_walk）マニフェストテンプレ（run root）

このテンプレは `/toc-immersive-ride --experience cloud_island_walk` の `output/<topic>_<timestamp>/video_manifest.md` 用。

```yaml
video_metadata:
  topic: "<topic>"
  source_story: "output/<topic>_<timestamp>/story.md"
  created_at: "<ISO8601>"
  duration_seconds: 0   # filled after narration is generated (optional)
  experience: "cloud_island_walk"
  aspect_ratio: "16:9"
  resolution: "1280x720"
  frame_rate: 24

assets:
  character_bible: []

  style_guide:
    visual_style: "実写、シネマティック、プラクティカルエフェクト（実物セット感）"
    forbidden:
      - "アニメ調"
      - "漫画調"
      - "イラスト調"
      - "絵"
      - "三人称"
      - "肩越し"
      - "自撮り"
      - "カメラが被写体を向く構図"
      - "画面内テキスト"
      - "字幕"
      - "ウォーターマーク"
      - "ロゴ"
    reference_images: []

  # 舞台装置/主役級アイテム bible（任意だが強く推奨）
  # cloud_island_walk では、抽象概念は “物理メタファー” の舞台装置/アイテムに落とし込む。
  object_bible: []
  # - object_id: "tbd_metaphor_gate"
  #   kind: "setpiece"
  #   reference_images:
  #     - "assets/objects/tbd_metaphor_gate.png"
  #   reference_variants:
  #     - variant_id: "tbd_metaphor_gate_activated"
  #       reference_images:
  #         - "assets/objects/tbd_metaphor_gate_activated.png"
  #       fixed_prompts:
  #         - "発光や開口など、状態差分だけを追加"
  #   fixed_prompts:
  #     - "実写的な材質/構造（SFのHUDは禁止、文字看板は禁止）"
  #     - "形/光/動きで比喩が読める（ラベルで説明しない）"
  #   cinematic:
  #     role: "映画での役割（境界/誘惑/啓示など）"
  #     visual_takeaways:
  #       - "映像から観客に与える情報（文字なしで理解できる形にする）"
  #     spectacle_details:
  #       - "見せ場ディテール（可動構造、隠し部屋、ショー等。メイン筋と無関係でもOK）"
  #   notes: null

scenes:
  # scene静止画 + つなぎ動画（ガイドは音声のみ）
  #
  # ゾーン設計（推奨）:
  # - Zones: 4–10 (minimum is 起承転結 = 4)
  # - Scenes per zone: 3–10
  #
  # scene_id の付け方（推奨）:
  # - Zone 1: 110,120,130...
  # - Zone 2: 210,220,230...
  # - Zone 3: 310,320,330...
  # - Zone 4: 410,420,430...
  #
  # 注意:
  # - 画面内テキストなし。すべて映像/比喩で伝える。
  # - 手元アンカーは必須ではない。構図（道を中央、水平線安定、カメラ高さ一定）で一人称連続性を担保する。
  - scene_id: 10
    timestamp: "00:00-00:08"
    image_generation:
      # review metadata は image_prompt_collection.md 側で持つ。
      # subagent false には reason key を必ず残し、fix 後に再 review する。
      # human_review_ok は例外許容の記録であり、subagent finding を消さない。
      # required block:
      # [全体 / 不変条件] / [登場人物] / [小道具 / 舞台装置] / [シーン] / [連続性] / [禁止]
      # 1 つでも欠けていれば subagent review は false にする。
      tool: "google_nanobanana_2"
      character_ids: []
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        一人称POVで前進しながら歩く。水平線は安定、カメラ高さ一定、自然な歩行。
        道/導線は常に中央（前進の連続性アンカー）。
        雲海の上に浮かぶ楽園の島（実物セット感。SFのHUDは禁止）。
        実写、シネマティック、実物セット感。自然な映画照明。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [小道具 / 舞台装置]

        [シーン]
        到着: 柔らかな雲を抜け、浮遊する石の道に出る。道の先に光る門が見える。
        見せ場: 最初のランドマークが <topic> の核心を“物理メタファー”で示す（文字は禁止）。
        構図: 道は中央、門は中景、雲海は遠景。前景は石/苔/霧など実物テクスチャ。

        [連続性]
        次への仕込み: 道は奥へ続き、光は少し暖色へ。前進方向とカメラ高さは維持。

        [禁止]
        アニメ/漫画/イラスト調。手の崩れ、指の増殖。あらゆる文字要素。
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
      motion_prompt: "浮遊する石の道を滑らかに前進して歩く。雲はゆっくり流れる。POVと構図の安定を維持。"
      output: "assets/scenes/scene10_to_20.mp4"
    audio:
      narration:
        contract:
          target_function: ""
          must_cover: []
          must_avoid: []
          done_when: []
        # review metadata は audio.narration.review に保持する。
        text: "TODO: ナレーション全文"
        tool: "elevenlabs"
        output: "assets/audio/narration.mp3"
        normalize_to_scene_duration: false

  - scene_id: 20
    timestamp: "00:08-00:16"
    image_generation:
      tool: "google_nanobanana_2"
      character_ids: []
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        一人称POVで前進しながら歩く。水平線は安定、カメラ高さ一定、自然な歩行。
        道/導線は常に中央。雲海の上に浮かぶ楽園の島。実写、シネマティック、実物セット感。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [小道具 / 舞台装置]

        [シーン]
        ゾーン1: <topic> の最初の核心を体で理解する“基礎”エリア（庭園/図書館/神殿など）。
        見せ場: 鏡、重り、橋、結び目などの“触れられる比喩オブジェクト”へ近づく（文字で説明しない）。
        構図: 比喩オブジェクトは中景。さらに奥へ続く道を遠景に置き、導線は中央を維持。

        [連続性]
        前と一致: 前進方向、カメラ高さ、照明方向。
        次への仕込み: 道が緩やかに曲がり、より複雑な“逆説”ゾーンへ導く。

        [禁止]
        アニメ/漫画/イラスト調。手の崩れ、指の増殖。あらゆる文字要素。
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
      motion_prompt: "前進を継続。微細な視差。構図とPOVの安定を維持。雲海がゆっくり流れる。"
      output: "assets/scenes/scene20_to_30.mp4"

  - scene_id: 30
    timestamp: "00:16-00:24"
    image_generation:
      tool: "google_nanobanana_2"
      character_ids: []
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        一人称POVで前進しながら歩く。水平線は安定、カメラ高さ一定、自然な歩行。
        道/導線は常に中央。雲海の上に浮かぶ楽園の島。実写、シネマティック、実物セット感。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [小道具 / 舞台装置]

        [シーン]
        ゾーン2: “逆説/緊張”エリア。2つの考えが物理建築として衝突する（交差する橋、ループする階段、逆流する水など）。
        見せ場: <topic> の深い対立が“構造の複雑さ”として感じられる（言葉で説明しない）。
        構図: 逆説構造は中景。静かな頂上の目的地を遠景に置く。導線は中央を維持。

        [連続性]
        前と一致: POVと前進方向、カメラ高さ。
        次への仕込み: “統合/解決”へ向かう明確な道筋が見えるようにする。

        [禁止]
        アニメ/漫画/イラスト調。手の崩れ、指の増殖。あらゆる文字要素。
      output: "assets/scenes/scene30.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null
```
