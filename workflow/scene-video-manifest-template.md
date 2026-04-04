# scene単体: 動画マニフェストテンプレ

このテンプレは `output/<topic>_<timestamp>/scenes/sceneXX/video_manifest.md` 用。

```yaml
video_metadata:
  topic: "<topic>"
  source_run: "output/<topic>_<timestamp>/"
  source_scene_script: "output/<topic>_<timestamp>/scenes/sceneXX/script.md"
  created_at: "<ISO8601>"
  duration_seconds: 30
  aspect_ratio: "9:16"
  resolution: "1080x1920"

assets:
  style_guide:
    visual_style: "tbd"
    reference_images: []

  # 主役級アイテム / 舞台装置（任意だが推奨）
  object_bible: []
  # - object_id: "tbd_setpiece"
  #   kind: "setpiece"  # setpiece|artifact|phenomenon
  #   reference_images:
  #     - "assets/objects/tbd_setpiece.png"
  #   fixed_prompts:
  #     - "材質/構造/機構の不変条件"
  #     - "文字/看板/銘板なし。形/光/動きで見せる"
  #   cinematic:
  #     role: "映画での役割"
  #     visual_takeaways:
  #       - "映像だけで伝えるべき情報"
  #     spectacle_details:
  #       - "見せ場ディテール"

scenes:
  - scene_id: 1
    timestamp: "00:00-00:30"
    # カット設計ルール（推奨）:
    # - 1カット = 1ナレーション
    # - メインカット（最低1つ）: 5–15秒（ナレーションの実秒ベース）
    # - サブカット（任意）: 3–15秒（短尺3–4秒はサブのみ。単一カットのナレーションで3秒は使わない）
    cuts:
      - cut_id: 1
        cut_role: "main"  # main|sub
        image_generation:
          # 新規の静止画は、連続性アンカーを作る cut だけに集中させる。
          # それ以外は、既存の参照画像や直前 cut の anchor frame を再利用してよい。
          # review metadata は image_generation.review 側で管理する:
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
          # false reason は修正対象を示し、fix 後に subagent が true へ戻す。
          # required block:
          # [全体 / 不変条件] / [登場人物] / [小道具 / 舞台装置] / [シーン] / [連続性] / [禁止]
          # 1 つでも欠けていれば subagent review は false にする。
          # tool: "google_nanobanana_pro"
          # tool: "seadream"        # Seedream 4.5 (OpenAI Images compatible; see SEADREAM_* env)
          tool: "google_nanobanana_pro"
          character_ids: ["character_id_here"]  # Use [] for B-roll scenes with no characters visible
          character_variant_ids: []  # Optional: pick a specific state/time variant for the active character(s)
          object_ids: []  # Use [] when no item / setpiece anchor is needed
          object_variant_ids: []  # Optional: pick a specific object/setpiece variant when needed
          prompt: |
            [全体 / 不変条件]
            TODO: スタイル/POVの不変条件。画面内テキストなし、字幕なし、ウォーターマークなし。

            [登場人物]
            TODO: 誰が映るか + 参照一致ルール（必要なら）。

            [シーン]
            TODO: 舞台 + 見せ場 + 構図（前景/中景/遠景）。

            [連続性]
            TODO: 前と一致 / 次への仕込み。

            [禁止]
            TODO: 禁止（例: 文字/ウォーターマーク/ロゴ + 望まないスタイル）。
          output: "assets/scenes/scene1_cut1_base.png"
          iterations: 4
          selected: null
        video_generation:
          # tool: "google_veo_3_1"  # disabled; routed to Kling for safety
          # tool: "kling_3_0"
          # tool: "kling_3_0_omni"
          # tool: "seedance"       # BytePlus ModelArk Seedance (video; see ARK_* env)
          tool: "kling_3_0"
          duration_seconds: 15
          input_image: "assets/scenes/scene1_cut1_base.png"
          motion_prompt: "TODO: カメラ/動き"
          output: "assets/scenes/scene1_cut1_video.mp4"
        audio:
          narration:
            contract:
              target_function: ""
              must_cover: []
              must_avoid: []
              done_when: []
            # review metadata は audio.narration.review に保持する。
            text: "TODO: ナレーション（メイン=5–15秒。複数カットなら Part 1/2 等）"
            tool: "elevenlabs"
            output: "assets/audio/scene1_cut1_narration.mp3"
            normalize_to_scene_duration: false
      - cut_id: 2
        cut_role: "sub"  # main|sub
        image_generation:
          # 新規生成を前提にしない。必要なときだけ anchor を更新する。
          # required block:
          # [全体 / 不変条件] / [登場人物] / [小道具 / 舞台装置] / [シーン] / [連続性] / [禁止]
          tool: "google_nanobanana_pro"
          character_ids: ["character_id_here"]
          character_variant_ids: []
          object_ids: []
          object_variant_ids: []
          prompt: |
            [全体 / 不変条件]
            TODO: 前と同じスタイル/禁止。画面内テキストなし。

            [登場人物]
            TODO: 誰が映るか + 参照一致ルール（必要なら）。

            [小道具 / 舞台装置]
            TODO: 必須の小道具 / 舞台装置（無ければ空 block を残す）。

            [シーン]
            TODO: 続き（結論/根拠/締め）。

            [連続性]
            TODO: 前 cut / 次 cut とどうつなぐか。

            [禁止]
            TODO: 禁止（例: 文字/ウォーターマーク/ロゴ + 望まないスタイル）。
          output: "assets/scenes/scene1_cut2_base.png"
          iterations: 4
          selected: null
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 15
          input_image: "assets/scenes/scene1_cut2_base.png"
          motion_prompt: "TODO: カメラ/動き"
          output: "assets/scenes/scene1_cut2_video.mp4"
        audio:
          narration:
            contract:
              target_function: ""
              must_cover: []
              must_avoid: []
              done_when: []
            # review metadata は audio.narration.review に保持する。
            text: "TODO: ナレーション（サブ=3–15秒。短尺3–4秒はサブカットとしてのみ使用）"
            tool: "elevenlabs"
            output: "assets/audio/scene1_cut2_narration.mp3"
            normalize_to_scene_duration: false
    text_overlay:
      main_text: "<main_text>"
      sub_text: "<question>"

final_output:
  video_file: "video.mp4"
  thumbnail: "thumb.png"

quality_check:
  visual_consistency: false
  audio_sync: false
  subtitle_readable: false
  aspect_ratio_correct: true
```
