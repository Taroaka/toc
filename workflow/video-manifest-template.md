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
      review_aliases: ["主人公"]
      physical_scale:
        height_cm: 175
        silhouette_notes:
          - "成人の自然な体格。scene をまたいでも身長感と骨格を変えない"
      relative_scale_rules:
        - "他キャラクターと同フレームにいるときも、主人公の体格を scene 間で変えない"
      reference_variants:
        - variant_id: "protagonist_battle_damaged"
          reference_images:
            - "assets/characters/protagonist_battle_damaged_front.png"
            - "assets/characters/protagonist_battle_damaged_side.png"
          fixed_prompts:
            - "右肩の布が裂け、軽い泥汚れがある"
      fixed_prompts:
        - "黒髪の短髪"
        - "和装（実写的な生地感）"

  style_guide:
    visual_style: "cinematic, warm tones"
    reference_images:
      - "assets/styles/reference_1.png"

  # 主役級アイテム / 舞台装置（任意だが推奨）
  # 竜宮城/玉手箱のような要素は character bible と同じく固定して扱う。
  object_bible: []
  location_bible: []
  # - location_id: "sea_temple"
  #   reference_images:
  #     - "assets/locations/sea_temple.png"
  #   reference_variants: []
  #   fixed_prompts:
  #     - "stone temple deep undersea"
  #   review_aliases: ["海底神殿"]
  #   continuity_notes:
  #     - "後続 cut でも同じ祭壇配置を維持する"
  #   notes: ""
  # - object_id: "tamatebako"
  #   kind: "artifact"  # setpiece|artifact|phenomenon
  #   reference_images:
  #     - "assets/objects/tamatebako_closeup.png"
  #   fixed_prompts:
  #     - "箱の材質/構造の不変条件"
  #     - "文字で説明せず、形/光/動きで魅力と危うさを伝える"
  #   cinematic:
  #     role: "贈与 + 禁忌 + 代償"
  #     visual_takeaways:
  #       - "開けたくなるが、開けると何かが起こる"
  #     spectacle_details:
  #       - "封印が呼吸するように発光する"

# === シーン別素材 ===
human_change_requests: []

scenes:
  - scene_id: 1   # dotted numeric string も可: 3.1
    timestamp: "00:00-00:10"
    implementation_trace:
      source_request_ids: []
      status: "implemented|verified|waived"
      notes: ""
    # カット設計ルール（推奨）:
    # - 1カット = 1ナレーション
    # - メインカット（最低1つ）: 5–15秒（ナレーションの実秒ベース）
    # - サブカット（任意）: 3–15秒（短尺3–4秒はサブのみ。単一カットのナレーションで3秒は使わない）
    cuts:
      - cut_id: 1  # dotted numeric string も可: 2.1
        cut_role: "main"  # main|sub
        cut_status: "active|deleted"
        deletion_reason: ""
        implementation_trace:
          source_request_ids: []
          status: "implemented|verified|waived"
          notes: ""
        scene_contract:
          target_beat: "string"     # この cut で何を伝えるか
          must_show: ["string"]     # image prompt / motion / narration のどこかで必ず見せる
          must_avoid: ["string"]    # この cut に入れてはいけない drift
          done_when: ["string"]     # evaluator と共有する完了条件
        image_generation:
          # 新規の静止画は、連続性アンカーが必要なときだけ優先して作る。
          # 既存の参照画像や前cutの anchor frame を再利用できる場合は、新規生成を強制しない。
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
          # human_review:
          #   status: "pending|approved|changes_requested"
          #   notes: ""
          #   change_requests:
          #     - request_id: "hr-001"
          #       status: "open|accepted|rejected|deferred|resolved"
          #       category: "story_alignment|reveal|subject_specificity|continuity|craft|other"
          #       requested_change: ""
          #       rationale: ""
          #       proposed_patch: ""
          #       requested_at: "ISO8601"
          #       resolved_at: ""
          #       resolution_notes: ""
          # 現行表記で agent_review_reason_codes を使っていても、意味は reason_keys と同じに保つ。
          # subagent は不足 entry を false にし、fix 後に再 review して true へ戻す。
          # human_review_ok は finding を理解して例外許容した記録であり、subagent false を上書きしない。
          # human_review は通常の修正要求フローの正本であり、override の代替にしない。
          # required block:
          # [全体 / 不変条件] / [登場人物] / [小道具 / 舞台装置] / [シーン] / [連続性] / [禁止]
          # 1 つでも欠けていれば subagent review は false にする。
          # tool: "google_nanobanana_2"
          # tool: "seadream"        # Seedream 4.5 (OpenAI Images compatible; see SEADREAM_* env)
          tool: "google_nanobanana_2"
          character_ids: ["protagonist"]  # Use [] when no character is visible
          character_variant_ids: []         # Optional: ["protagonist_battle_damaged"] when a specific state/time variant is needed
          object_ids: []                    # Use [] when no setpiece / prop anchor is required
          object_variant_ids: []            # Optional: choose a specific object/setpiece variant when defined in assets.object_bible[]
          location_ids: []                  # Optional: reusable location anchors from assets.location_bible[]
          location_variant_ids: []          # Optional: location state/time variant
          applied_request_ids: []
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
        still_image_plan:
          mode: "generate_still|reuse_anchor|no_dedicated_still"
          generation_status: "missing|created|recreate"
          rationale: ""
          source: ""
        still_assets:
          - asset_id: "scene1_cut1_base"
            role: "primary"
            output: "assets/scenes/scene1_cut1_base.png"
            derived_from_asset_ids: []
            reference_asset_ids: []
            reference_usage: []
            direction_notes: []
            applied_request_ids: []
            implementation_trace:
              source_request_ids: []
              status: "implemented|verified|waived"
              notes: ""
            image_generation:
              tool: "google_nanobanana_2"
              character_ids: ["protagonist"]
              object_ids: []
              location_ids: []
              prompt: "same as primary image prompt"
              output: "assets/scenes/scene1_cut1_base.png"
        video_generation:
          # tool: "google_veo_3_1"  # disabled; routed to Kling for safety
          # tool: "kling_3_0"
          # tool: "kling_3_0_omni"
          # tool: "seedance"       # BytePlus ModelArk Seedance (video; see ARK_* env)
          tool: "kling_3_0"
          duration_seconds: 10
          input_image: "assets/scenes/scene1_cut1_base.png"
          input_asset_id: "scene1_cut1_base"
          first_frame_asset_id: ""
          last_frame_asset_id: ""
          reference_asset_ids: []
          direction_notes: []
          continuity_notes: []
          applied_request_ids: []
          motion_prompt: "ゆっくりパン（落ち着いた速度、微細な視差）"
          output: "assets/scenes/scene1_cut1_video.mp4"
        audio:
          narration:
            contract:
              target_function: "opening_setup"
              must_cover: ["桃から生まれた"]
              must_avoid: ["カメラ", "ズーム"]
              done_when: ["物語の導入として自然に読める", "scene/script の出来事を素直に伝える"]
            # 映像価値を優先する追加 cut で narration を入れない場合は
            # tool: "silent" と silence_contract を必ずセットで持たせる:
            # silence_contract:
            #   intentional: true
            #   kind: "visual_value_hold"
            #   confirmed_by_human: true
            #   reason: "映像で見せる価値が大きい追加カット"
            # review metadata は audio.narration.review 側で持つ:
            # review:
            #   agent_review_ok: true
            #   agent_review_reason_keys: []
            #   agent_review_reason_messages: []
            #   human_review_ok: false
            #   human_review_reason: ""
            # human_review:
            #   status: "pending|approved|changes_requested"
            #   notes: ""
            #   change_requests:
            #     - request_id: "hr-001"
            #       status: "open|accepted|rejected|deferred|resolved"
            #       category: "naturality|reveal|pronunciation|story_alignment|timing|other"
            #       requested_change: ""
            #       rationale: ""
            #       suggested_text: ""
            #       suggested_tts_text: ""
            #       requested_at: "ISO8601"
            #       resolved_at: ""
            #       resolution_notes: ""
            text: "むかし、ある むらに ももから うまれた しょうねんが いました。"
            tts_text: "むかし、ある むらに ももから うまれた しょうねんが いました。"
            tool: "elevenlabs"
            applied_request_ids: []
            implementation_trace:
              source_request_ids: []
              status: "implemented|verified|waived"
              notes: ""
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
  review_contract:
    target_outcome: "publishable_short|draft_review|internal_preview"
    must_have_artifacts: ["video.mp4"]
    must_avoid: ["string"]
    done_when: ["string"]
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
