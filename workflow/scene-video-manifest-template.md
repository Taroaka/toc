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

scenes:
  - scene_id: 1
    timestamp: "00:00-00:30"
    # Cut planning rule (recommended):
    # - 1 cut = 1 narration
    # - main cut (at least 1): 5–15 seconds (based on narration actual duration)
    # - sub cuts (optional): 3–15 seconds (short 3–4s cuts are sub-only; not for single-cut narration)
    cuts:
      - cut_id: 1
        cut_role: "main"  # main|sub
        image_generation:
          # tool: "google_nanobanana_pro"
          # tool: "seadream"        # Seedream 4.5 (OpenAI Images compatible; see SEADREAM_* env)
          tool: "google_nanobanana_pro"
          character_ids: ["character_id_here"]  # Use [] for B-roll scenes with no characters visible
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
            text: "TODO: ナレーション（メイン=5–15秒。複数カットなら Part 1/2 等）"
            tool: "elevenlabs"
            output: "assets/audio/scene1_cut1_narration.mp3"
            normalize_to_scene_duration: false
      - cut_id: 2
        cut_role: "sub"  # main|sub
        image_generation:
          tool: "google_nanobanana_pro"
          character_ids: ["character_id_here"]
          prompt: |
            [全体 / 不変条件]
            TODO: 前と同じスタイル/禁止。画面内テキストなし。

            [シーン]
            TODO: 続き（結論/根拠/締め）。
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
