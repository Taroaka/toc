# 動画マニフェスト: テンプレート

`docs/video-generation.md` の出力スキーマに準拠した作業テンプレートです。

- 出力先: `output/videos/<topic>_<timestamp>_manifest.md`
  - 1物語1フォルダ運用の場合: `output/<topic>_<timestamp>/video_manifest.md`
- 目的: 生成素材・選定・合成の管理

```yaml
# === メタ情報 ===
video_metadata:
  topic: "<topic>"
  source_story: "output/<topic>_<timestamp>/story.md"
  created_at: "<ISO8601>"
  duration_seconds: 60
  aspect_ratio: "9:16"
  resolution: "1080x1920"

# === 素材管理 ===
assets:
  character_bible:
    - character_id: "protagonist"
      reference_images:
        - "assets/characters/protagonist_front.png"
        - "assets/characters/protagonist_side.png"
        - "assets/characters/protagonist_back.png"
      fixed_prompts:
        - "黒髪の短髪"
        - "和装（実写的な生地感）"

  style_guide:
    visual_style: "cinematic, warm tones"
    reference_images:
      - "assets/styles/reference_1.png"

# === シーン別素材 ===
scenes:
  - scene_id: 1
    timestamp: "00:00-00:10"
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
          prompt: |
            [全体 / 不変条件]
            シネマティック。暖色寄り。自然な照明。画面内テキストなし、字幕なし、ウォーターマークなし。

            [シーン]
            夜明けの静かな田舎の村。柔らかな朝霧。広い導入ショット。

            [禁止]
            文字、ウォーターマーク、ロゴ。
          output: "assets/scenes/scene1_cut1_base.png"
          iterations: 4
          selected: 1
        video_generation:
          # tool: "google_veo_3_1"  # disabled; routed to Kling for safety
          # tool: "kling_3_0"
          # tool: "kling_3_0_omni"
          # tool: "seedance"       # BytePlus ModelArk Seedance (video; see ARK_* env)
          tool: "kling_3_0"
          duration_seconds: 10
          input_image: "assets/scenes/scene1_cut1_base.png"
          motion_prompt: "ゆっくりパン（落ち着いた速度、微細な視差）"
          output: "assets/scenes/scene1_cut1_video.mp4"
        audio:
          narration:
            text: "昔、ある村に桃から生まれた少年がいました。"
            tool: "elevenlabs"
            output: "assets/audio/scene1_cut1_narration.mp3"
            normalize_to_scene_duration: false
          bgm:
            source: "assets/audio/bgm_intro.mp3"
            volume: 0.3
          sfx: []

# === 最終出力 ===
final_output:
  video_file: "output/<topic>_<timestamp>/video.mp4"
  thumbnail: "output/<topic>_<timestamp>/thumb.png"

# === 品質チェック ===
quality_check:
  visual_consistency: false
  audio_sync: false
  subtitle_readable: false
  aspect_ratio_correct: true
```

---

## 参考コマンド（結合/レンダリング）

`scripts/render-video.sh` を利用する場合の例:

```bash
scripts/render-video.sh \
  --clip-list clips.txt \
  --narration narration.mp3 \
  --bgm bgm.mp3 \
  --srt subtitles.srt \
  --out output/<topic>_<timestamp>/video.mp4
```
