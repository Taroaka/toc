# scene単体: 動画マニフェストテンプレ（改善版）

このテンプレは `output/<topic>_<timestamp>/scenes/sceneXX/video_manifest.md` 用。
scene 単体 run でも、p400 の cinematic scene contract → p600 still → p800 motion の責務を崩さない。

```yaml
manifest_phase: "production"
video_metadata:
  topic: "<topic>"
  source_run: "output/<topic>_<timestamp>/"
  source_scene_script: "output/<topic>_<timestamp>/scenes/sceneXX/script.md"
  created_at: "<ISO8601>"
  duration_seconds: 30
  aspect_ratio: "9:16"
  resolution: "1080x1920"

assets:
  character_bible: []
  style_guide:
    visual_style: "実写映画調、自然な映画照明、実物セット感"
    reference_images: []
    forbidden:
      - "画面内テキスト"
      - "字幕"
      - "ウォーターマーク"
      - "ロゴ"
      - "アニメ/漫画/イラスト調"
  object_bible: []
  location_bible: []

human_change_requests: []

scenes:
  - scene_id: 1
    timestamp: "00:00-00:30"
    scene_intent:
      importance: "medium"
      target_duration_seconds: 30
      estimated_duration_seconds: 30
      story_purpose: "この scene が物語全体で担う役割"
      dramatic_question: "この scene の間、観客が追う問い"
      scene_spine: "setup → pressure → turn → payoff → handoff の1文要約"
      value_shift:
        from: "開始時の状態"
        to: "終了時の状態"
        visible_evidence:
          - "画面だけで変化が読める証拠"
      causal_turn: "次 scene を発生させる不可逆の出来事/決断/発見"
      audience_information: []
      withheld_information: []
      reveal_constraints: []
      affect_transition: "観客感情の変化"
      visual_thesis: "この scene を代表する映画的な一枚絵"
      handoff_to_next_scene: "terminal_resolution または次sceneへのアンカー"
      production_risks: []
      handoff_notes:
        p500_asset: []
        p600_image: []
        p700_narration: []
        p800_video: []
      coverage_review:
        audience_information_covered: false
        visualizable_action_covered: false
        value_shift_visible: false
        causal_turn_visible: false
        next_scene_connection_checked: false

    # カット設計ルール:
    # - 1カット = 1意図。
    # - production scene は原則3カット以上。low importance は2カット以上、high/critical は5カット以上。
    # - target_duration_seconds / 8 を切り上げたカット数を下回らない。
    # - cut_contract が正本。scene_contract は既存 reader 向け互換 alias。
    cuts:
      - cut_id: 1
        cut_role: "main"
        cut_status: "active"
        cut_contract:
          schema_version: "2.1"
          cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
          viewer_contract:
            target_beat: "この cut で観客に体験させる1つのこと"
            screen_question: "この cut の間、観客が画面から読む問い"
            dramatic_job: "scene全体のどこを担当するか"
            emotional_micro_shift: {from: "", to: ""}
            visual_proof: "映像だけで target_beat が成立したと分かる証拠"
            must_show: []
            must_avoid: []
            done_when: []
          cinematic_contract:
            camera_intent: "観客の視線をどこへ導くか"
            subject_priority: {primary: "", secondary: "", background: ""}
            screen_geography: {foreground: "", midground: "", background: "", screen_direction: ""}
          continuity_contract:
            start_state: {}
            end_state: {}
            carry_forward_to_next_cut: []
          first_frame_contract:
            imageable: true
            first_frame_brief: "動画が動き出す直前に見えている初期状態。prompt本文に制作メタは入れない"
            action_completion_state: "pre_action|early_action|mid_action|aftermath|hold"
          motion_contract:
            movable: true
            motion_brief: "p800 motion prompt 専用。p600 image prompt authoring では参照しない"
            end_state: "次 cut へ渡す最後の状態"
            must_not_add: []
          narration_contract:
            speakable_or_silent: true
            role: "setup|fact|emotion|contrast|aftertaste|silent"
            target_function: "この声が cut で果たす役割"
            text: ""
            tts_text: ""
            silence_reason: ""
          downstream_handoff:
            p500_asset: {}
            p600_image: {}
            p700_narration: {}
            p800_video: {}
            carries_to_next_cut: []
            carries_to_next_scene: []
        scene_contract:
          cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
          target_beat: "この cut で伝える1つのこと"
          screen_question: "観客が画面から読む問い"
          dramatic_job: "scene全体のどこを担当するか"
          visual_beat: "画として何が見えるか"
          first_frame_brief: "動画が動き出す直前に見えている初期状態。prompt本文に制作メタは入れない"
          motion_brief: "p800 motion prompt 専用。p600 image prompt authoring では参照しない"
          must_show: []
          must_avoid: []
          done_when: []
        image_generation:
          tool: "codex_builtin_image"
          character_ids: []
          character_variant_ids: []
          object_ids: []
          object_variant_ids: []
          location_ids: []
          location_variant_ids: []
          applied_request_ids: []
          prompt_authoring_context:
            image_role: "video_first_frame_candidate"
            first_frame_question: "この動画がこの静止画から動き出すなら、冒頭で何が見えているべきか"
            api_prompt_policy: "do_not_include_authoring_context"
          contract:
            target_focus: "character|relationship|setpiece|blocking|environment"
            must_include: []
            must_avoid: []
            done_when: []
          review:
            agent_review_ok: false
            agent_review_reason_keys: []
            agent_review_reason_messages: []
            rubric_scores: {}
            overall_score: 0.0
            human_review_ok: false
            human_review_reason: ""
            triangulation_review:
              same_target_beat: false
              image_supports_motion_start: false
              motion_reaches_declared_end_state: false
              narration_not_captioning_image: false
              reveal_constraints_preserved: false
              continuity_preserved: false
              handoff_visible_or_audible: false
          prompt: |
            [全体 / 不変条件]
            実写映画調、自然な映画照明、実物セット感。画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

            [登場人物]
            TODO: 映る人物を具体化する。人物が映らない場合は「人物なし。背景人物も入れない」と書く。

            [小道具 / 舞台装置]
            TODO: 必須の小道具・舞台装置・場所アンカーを書く。無い場合も「この場面で主役級の小道具はない」と明示する。

            [シーン]
            舞台: TODO。
            主役: TODO。
            前景: TODO。
            中景: TODO。
            背景: TODO。
            光: TODO。
            構図: TODO。

            [連続性]
            TODO: この画像だけで読み取れる人物状態・場所・進行方向・次へのアンカーを書く。前cutの記憶に依存しない。

            [禁止]
            画面内テキスト、字幕、ウォーターマーク、ロゴ、アニメ調、漫画調、イラスト調、人物や手の崩れ、reveal早出し。
          output: "assets/scenes/scene1_cut1_base.png"
          iterations: 4
          selected: null
        still_image_plan:
          mode: "generate_still|reuse_anchor|no_dedicated_still"
          generation_status: "missing|created|recreate"
          rationale: ""
          source: ""
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 10
          input_image: "assets/scenes/scene1_cut1_base.png"
          input_asset_id: "scene1_cut1_base"
          first_frame_asset_id: ""
          last_frame_asset_id: ""
          reference_asset_ids: []
          motion_prompt: |
            cut_function: <scene_contract.cut_function>
            camera: TODO
            subject_motion: TODO
            environment_motion: TODO
            emotional_change: TODO
            end_state: TODO
            avoid: 新キャラ追加、重要道具の追加、reveal早出し、画面内テキスト、過剰なズーム。
          output: "assets/scenes/scene1_cut1_video.mp4"
        audio:
          narration:
            contract:
              target_function: "setup|fact|emotion|contrast|aftertaste|silent"
              must_cover: []
              must_avoid: []
              done_when: []
            text: "TODO: ナレーション。silent cut の場合は空文字にし、tool: silent と silence_contract を持つ。"
            tts_text: "TODO"
            tool: "elevenlabs"
            output: "assets/audio/scene1_cut1_narration.mp3"
            normalize_to_scene_duration: false

final_output:
  video_file: "video.mp4"
  thumbnail: "thumb.png"

quality_check:
  review_contract:
    target_outcome: "publishable_short|draft_review|internal_preview"
    must_have_artifacts: ["video.mp4"]
    must_avoid: []
    done_when: []
  scene_value_shift_visible: false
  causal_turn_visible: false
  visual_consistency: false
  audio_sync: false
  aspect_ratio_correct: true
```
