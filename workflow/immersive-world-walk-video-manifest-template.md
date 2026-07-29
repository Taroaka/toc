# 没入型: 既存世界観を散歩する体験（world_walk）マニフェストテンプレ（run root）

このテンプレは `/toc-world-walk` または `/toc-immersive-ride --experience world_walk` の `output/<topic>_<timestamp>/video_manifest.md` 用。
既存 run の `story.md` / `assets/` を参照し、「世界観を散歩してみた」形式で、観察者が少し離れて世界内を歩く。

```yaml
manifest_phase: skeleton
video_metadata:
  topic: "<topic>"
  source_story: "<source_story>"
  source_run: "<source_run>"
  source_assets: "<source_assets>"
  created_at: "<ISO8601>"
  duration_seconds: 0
  experience: "world_walk"
  aspect_ratio: "16:9"
  resolution: "1280x720"
  frame_rate: 24

assets:
  # source_run の既存 asset を正本として使う。ここには必要に応じて source asset のパスを転記する。
  character_bible:
    # - character_id: "source_character"
    #   reference_images:
    #     - "<source_assets>/characters/source_character_front.png"
    #   fixed_prompts:
    #     - "参照画像と同一人物。観察者カメラから中景〜遠景で見える。"
    #   notes: "参照キャラが遠景に現れる場面で使う。"

  object_bible:
    # - object_id: "source_location_or_setpiece"
    #   kind: "location"
    #   reference_images:
    #     - "<source_assets>/objects/source_location_or_setpiece.png"
    #   fixed_prompts:
    #     - "既存 asset の材質・構造・色を維持する。文字看板で説明しない。"

  style_guide:
    visual_style: "実写、シネマティック、自然な歩行観察、生活感のある世界散歩"
    forbidden:
      - "アニメ調"
      - "漫画調"
      - "イラスト調"
      - "絵"
      - "派手な演出"
      - "爆発や戦闘を強調する演出"
      - "急接近"
      - "劇的な手持ちブレ"
      - "主人公本人の主観視点"
      - "自撮り"
      - "カメラが物語へ介入する構図"
      - "画面内テキスト"
      - "字幕"
      - "ウォーターマーク"
      - "ロゴ"
    reference_images: []

scenes:
  # world_walk の基本構成:
  # - 序盤: 物語が進まない asset 内散歩。既存世界の道具・建築・空気だけを観察する。
  # - 中盤: 参照キャラが遠景に現れる。ただしカメラは追いすぎず、少し遠目の観察者POVを維持する。
  # - 後半: 物語が別導線で始まっているのを遠くに見かける。観察者は介入しない。
  - scene_id: 10
    timestamp: "00:00-00:08"
    image_generation:
      tool: "google_nanobanana_2"
      character_ids: []
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        観察者POV。カメラは既存世界の中を静かに歩くが、主人公本人の視点ではない。
        少し遠目、中景〜遠景中心、自然な歩行速度、水平線安定、カメラ高さ一定。
        実写、シネマティック、自然光、生活感のある空気。派手な演出なし。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        まだ登場しない。人物なし。

        [小道具 / 舞台装置]
        source_run の既存 asset に基づく建築、道具、地面、壁、入口、生活痕跡。

        [シーン]
        物語が進まない asset 内散歩。観察者が世界の入口を歩き、建築や道具の質感を眺める。
        事件や会話は起こさない。観光客が少し離れて世界観を確かめるような静かな導入。
        構図: 通路や床の導線を中央に置き、遠景に次の場所への抜けを見せる。

        [連続性]
        次へ続く道が奥に見える。照明、進行方向、カメラ高さを維持する。

        [禁止]
        アニメ/漫画/イラスト調。派手なエフェクト、爆発、急接近、劇的な手持ちブレ。あらゆる文字要素。
      output: "assets/scenes/scene10.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null
    video_generation:
      tool: "kling_3_0"
      duration_seconds: 8
      first_frame: "assets/scenes/scene10.png"
      last_frame: "assets/scenes/scene20.png"
      motion_prompt: "観察者POVで静かに前進して歩く。中景〜遠景を保ち、派手な演出や急接近なし。世界内の質感をゆっくり見せる。"
      output: "assets/scenes/scene10_to_20.mp4"
    audio:
      narration:
        contract:
          target_function: "世界観散歩の導入"
          must_cover: ["既存世界へ入る感覚", "物語へ介入しない観察者の距離"]
          must_avoid: ["事件の説明を急ぐ", "画面内テキスト前提の説明"]
          done_when: ["観察者として歩き始めたことが伝わる"]
        text: ""
        tts_text: ""
        tool: "elevenlabs"
        output: "assets/audio/scene10_narration.mp3"
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
        観察者POV。少し遠目、中景〜遠景中心、自然な歩行速度、水平線安定。
        実写、シネマティック、生活感のある世界散歩。派手な演出なし。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        まだ登場しない。人物なし、または遠景の小さな通行人だけ。

        [小道具 / 舞台装置]
        source_run の既存 asset の内部。主役級の場所・建物・道具・地形を参照し、材質を維持する。

        [シーン]
        物語がまだ進まない散歩パートを継続。観察者は asset の中へ入り、壁面、床、光、手入れされた道具を見る。
        ここでは物語上の事件を起こさず、世界の生活と質感を見せる。
        構図: 手前に道具や柱、中景に通路、遠景に開けた場所。

        [連続性]
        前と同じ進行方向。遠景に人影が出そうな気配だけを残す。

        [禁止]
        主人公本人の主観視点、急接近、派手な演出、あらゆる文字要素。
      output: "assets/scenes/scene20.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null
    video_generation:
      tool: "kling_3_0"
      duration_seconds: 8
      first_frame: "assets/scenes/scene20.png"
      last_frame: "assets/scenes/scene30.png"
      motion_prompt: "静かな歩行を継続。観察者は内部を見回すが、カメラは中景〜遠景を保つ。事件は起こさない。"
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
        観察者POV。少し遠目、中景〜遠景中心、自然な歩行速度、水平線安定。
        実写、シネマティック、派手な演出なし。画面内テキストなし。

        [登場人物]
        参照キャラはまだ画面の主役にしない。遠景に現れる直前の気配だけ。

        [小道具 / 舞台装置]
        source_run の既存 location / setpiece / props を参照する。物語の気配が残るが、説明文字は使わない。

        [シーン]
        散歩の途中で、物語が別の場所で始まりそうな兆しを見る。小道具の位置、開いた扉、遠くの光などで示す。
        まだ直接の物語進行は見せない。観察者は立ち止まらず、少し離れて歩き続ける。

        [連続性]
        次に参照キャラが遠景に現れる。カメラは近づきすぎず、観察者の距離を保つ。

        [禁止]
        派手な伏線演出、急なズーム、主役への密着、あらゆる文字要素。
      output: "assets/scenes/scene30.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null
    video_generation:
      tool: "kling_3_0"
      duration_seconds: 8
      first_frame: "assets/scenes/scene30.png"
      last_frame: "assets/scenes/scene40.png"
      motion_prompt: "観察者POVでゆっくり進む。遠景に物語の気配を残し、派手な演出なしで次の場所へつなぐ。"
      output: "assets/scenes/scene30_to_40.mp4"

  - scene_id: 40
    timestamp: "00:24-00:32"
    image_generation:
      tool: "google_nanobanana_2"
      character_ids: ["source_character"]
      character_variant_ids: []
      object_ids: []
      object_variant_ids: []
      prompt: |
        [全体 / 不変条件]
        観察者POV。カメラは少し遠目に留まり、参照キャラへ急接近しない。
        実写、シネマティック、自然な歩行観察。派手な演出なし。
        画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

        [登場人物]
        source_run の参照キャラが遠景に現れる。顔・髪型・服装・体格は既存参照 asset と一致。
        参照キャラは中景〜遠景で見える。観察者には気づかず、物語の導線へ向かう。

        [小道具 / 舞台装置]
        source_run の既存 asset と同じ世界。参照キャラの周囲に、物語開始を示す小道具や場所を置く。

        [シーン]
        参照キャラが遠景に現れる。物語がそちらでは始まっているが、観察者は遠くから見かけるだけ。
        カメラは通路や広場の端を歩き、キャラクターの動きを横目で見る。会話や大事件を近くで見せない。

        [連続性]
        観察者はキャラを追いすぎず、世界の散歩を続ける。物語は遠景で進行し始める。

        [禁止]
        主人公本人の主観視点、肩越し密着、顔の大写し、急接近、派手な演出、あらゆる文字要素。
      output: "assets/scenes/scene40.png"
      aspect_ratio: "16:9"
      image_size: "1K"
      references: []
      iterations: 4
      selected: null
    video_generation:
      tool: "kling_3_0"
      duration_seconds: 8
      first_frame: "assets/scenes/scene40.png"
      last_frame: "assets/scenes/scene50.png"
      motion_prompt: "観察者POVで歩き続ける。参照キャラは遠景から中景に留め、物語が別導線で始まる様子を静かに見せる。"
      output: "assets/scenes/scene40_to_50.mp4"
```
