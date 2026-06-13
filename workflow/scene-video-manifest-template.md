# scene単体: 動画マニフェストテンプレ（改善版）

このテンプレは `output/<topic>_<timestamp>/scenes/sceneXX/video_manifest.md` 用。
scene 単体 run でも、p400 の cinematic scene contract → p600 still → p800 motion の責務を崩さない。
このファイルは skeleton テンプレートであり、TODO を含めてよい。production manifest へ昇格する時点では TODO / TBD / pending を残さない。

```yaml
manifest_phase: "skeleton"
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
    importance: "medium"
    target_duration_seconds: 30
    estimated_duration_seconds: 30
    handoff_to_next_scene: "terminal_resolution または次sceneへのアンカー"
    terminal_resolution: ""
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
      character_state:
        start: "開始時の人物/関係/身体状態"
        end: "終了時の人物/関係/身体状態"
        visible_behavior: []
      visual_thesis: "この scene を代表する映画的な一枚絵"
      handoff_to_next_scene: "terminal_resolution または次sceneへのアンカー"
      story_specificity:
        non_compressible_beat: "この scene を cut に圧縮してはいけない不可逆 beat"
        scene_promotion_reason: "独立した問い/価値変化/因果 turn を持つため scene に昇格させる理由"
        unique_scene_responsibility: "物語全体でこの scene だけが担う責務"
        actor_forces:
          protagonist: ""
          opposing: []
          helping: []
          observing: []
          pressure_method: ""
        meaning_ladder:
          protagonist_stage: ""
          relationship_stage: ""
          object_or_setpiece_stage: ""
        concrete_handoff:
          incoming_trigger: ""
          outgoing_anchor: ""
          outgoing_pressure: ""
        anti_template_language:
          banned_generic_phrases_absent: false
          story_specific_terms: []
          specificity_note: ""
      scene_conflict_engine:
        desire: ""
        obstacle: ""
        stakes: ""
        escalation: ""
        no_return_point: ""
        visible_pressure: []
      audience_knowledge_delta:
        before_scene: []
        learned_during_scene: []
        misdirected_or_reframed: []
        still_unknown_after_scene: []
        forbidden_early_reveals: []
      handoff_chain:
        incoming:
          anchor_id: ""
          anchor_type: "object|sound|gaze|gesture|threat|question|none"
          visible_or_audible_form: ""
        outgoing:
          anchor_id: ""
          anchor_type: "object|sound|gaze|gesture|threat|question|terminal"
          next_scene_selector: ""
          required_next_scene_start_pressure: ""
      object_arc: []
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
        scene_specificity_gate_passed: false
        next_scene_connection_checked: false

    # カット設計ルール:
    # - 1カット = 1意図。
    # - cut 数は固定テンプレートではなく scene_cut_coverage_plan で scene obligation から逆算する。
    # - low/medium/high/critical の重要度 floor と target_duration_seconds / 8 の duration floor を下回らない。
    # - 同じ story fact の繰り返しなら cut 追加ではなく既存 cut の prompt/contract を厚くする。
    # - cut_contract が正本。legacy_scene_contract_alias / scene_contract は既存 reader 向け互換 alias。
    scene_cut_coverage_plan:
      coverage_strategy: "reverse_from_scene_event"
      source_schema_version: "scene_event_v1"
      min_cut_count:
        by_importance: 3
        by_duration: 4
        by_event_beats: 4
        selected: 4
        exception_reason: ""
      event_beat_inventory:
        - beat_id: "scene1_event_setup"
          beat_function: "setup"
          must_be_seen: true
          assigned_cut_ids: []
      scene_obligations:
        - source: "dramatic_question|scene_event.event_sequence|value_shift.visible_evidence|causal_turn|reveal_constraints|handoff_to_next_scene"
          evidence: []
      cut_assignments:
        - cut_index: 1
          obligation_id: ""
          cut_function: "pressure|threshold|reveal|reaction|payoff|handoff|custom"
          event_assignment:
            source_event_contract:
              primary_event_beat_id: "scene1_event_setup"
              source_event_beat_ids: ["scene1_event_setup"]
          target_beat: ""
          visual_proof: ""
          audience_knowledge_delta: ""
          causal_proof: ""
          required_roles: []
          anti_redundancy_key: ""
    cuts:
      - cut_id: 1
        cut_role: "main"
        cut_status: "active"
        cut_contract:
          schema_version: "3.0"
          source_event_contract:
            primary_event_beat_id: "scene1_event_setup"
            source_event_beat_ids: ["scene1_event_setup"]
            event_beat_function: "setup"
            event_time_position: "before_trigger"
            source_event_summary: ""
            source_visible_action: ""
            source_visible_reaction: ""
            no_reaction_required_reason: ""
            source_required_visual_evidence: []
            event_facts_to_preserve: []
            event_facts_not_to_invent: []
            allowed_reveal_info_ids: []
            forbidden_reveal_info_ids: []
          cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
          intent_budget:
            primary_intent: ""
            assigned_obligation_ids: []
            secondary_intents_allowed: []
            forbidden_combined_intents:
              - "new_location_establishing + major_reveal + next_scene_handoff"
            overload_exception_reason: ""
          viewer_contract:
            target_beat: "この cut で観客に体験させる1つのこと"
            screen_question: "この cut の間、観客が画面から読む問い"
            dramatic_job: "scene全体のどこを担当するか"
            audience_knowledge_delta: "この cut を見た観客が scene 内で新しく理解すること"
            causal_proof: "この cut が因果や不可逆イベントを画面で証明する方法"
            visual_evidence: []
            required_roles: []
            anti_redundancy_key: "同 scene 内でこの cut だけが担当する意味"
            reveal_constraints:
              inherited_from_scene: []
              allowed_reveals_in_this_cut: []
              forbidden_until_later_cut: []
              forbidden_until_later_scene: []
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
            continuity_risks: []
          cut_handoff:
            receives_from_previous:
              anchor_id: ""
              anchor_type: "object|sound|gaze|gesture|movement|light|threat|question|none"
              visible_or_audible_form: ""
              expected_previous_cut_selector: ""
            delivers_to_next:
              anchor_id: ""
              anchor_type: "object|sound|gaze|gesture|movement|light|threat|question|terminal"
              visible_or_audible_form: ""
              expected_next_cut_selector: ""
          first_frame_contract:
            imageable: true
            source_event_beat_id: "scene1_event_setup"
            event_time_position: "before_trigger"
            event_fact_visible_in_still: ""
            not_yet_happened_in_still: []
            first_frame_brief: "動画が動き出す直前に見えている初期状態。prompt本文に制作メタは入れない"
            visible_start_state:
              character_state: ""
              prop_state: ""
              spatial_state: ""
              emotional_state: ""
              gaze_or_attention: ""
            motion_start_affordance:
              movable_subject: ""
              movement_vector: ""
              camera_start_reason: ""
            action_completion_state: "pre_action|early_action|mid_action|aftermath|hold"
            static_first_frame_rule: "motion の説明ではなく、静止画として読める証拠で cut の意味を開始する"
            must_be_static_evidence_not_motion: true
          motion_contract:
            movable: true
            source_event_beat_id: "scene1_event_setup"
            starts_from_first_frame: true
            must_not_advance_to_event_beat_ids: []
            motion_brief: "p800 motion prompt 専用。p600 image prompt authoring では参照しない"
            start_from_visible_state: ""
            end_state: "次 cut へ渡す最後の状態"
            end_frame_brief: ""
            must_not_add: []
          narration_contract:
            schema_version: "narration_contract_v2"
            speakable_or_silent: true
            source_event_beat_ids: ["scene1_event_setup"]
            allowed_info_ids: []
            forbidden_info_ids: []
            must_not_advance_to_event_beat_ids: []
            must_not_explain_visible_action_as_caption: true
            narration_event_boundary: "same_event_only"
            story_role:
              narrative_position: "opening|middle|ending"
              cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
              voice_function: "information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence"
              audience_state_before: ""
              audience_state_after: ""
              must_cover: []
              must_not_reveal: []
              done_when: []
            visual_distance:
              distance_policy: "stay_close|contextual|meaning_first|silent"
              visible_facts_in_frame: []
              narration_should_add: []
              must_not_caption_visible_action: true
              visual_overlap_allowed: false
              visual_overlap_reason: ""
            rhythm_and_timing:
              target_speech_seconds: 0
              min_speech_seconds: 0
              max_speech_seconds: 0
              start_timing: "immediate|after_visual_read|mid_cut|late_cut|none"
              end_timing: "before_cut_end|on_cut_end|after_visual_resolution|none"
              pause_intent: []
              audio_visual_sync_point: ""
            tts_readiness:
              normalization_policy: "kanji_public_hiragana_tts|mixed|dictionary_first"
              pronunciation_targets: []
              max_sentence_chars: 42
              tts_text_must_differ_from_text_when_needed: true
            # compatibility aliases for older readers
            role: "setup|fact|emotion|contrast|aftertaste|silent"
            target_function: "derive_from_story_role_voice_function"
            must_cover:
              - "derive_from_story_role_must_cover"
            must_avoid:
              - "映像のキャプション化"
            done_when:
              - "derive_from_story_role_done_when"
            timing_intent: ""
            silence_reason: ""
          rhythm_contract:
            expected_duration_seconds: 8
            pacing: "quick|standard|slow_hold|spectacle_hold"
            comprehension_moment: ""
            cut_out_reason: ""
            audio_visual_sync_point: ""
            duration_exception: {allowed: false, reason: ""}
          asset_dependency:
            character_ids_required: []
            object_ids_required: []
            location_ids_required: []
            variant_ids_required: []
            new_asset_requests: []
            reusable_anchor_ids: []
            reference_role: {}
          downstream_handoff:
            p500_asset:
              required_asset_ids: []
              asset_candidates: []
              continuity_anchor_needed: false
              new_asset_needed: false
              reuse_allowed: false
            p600_image:
              prompt_requirements: []
              reference_requirements: []
              first_frame_must_include: []
              first_frame_must_avoid: []
            p700_narration:
              narration_requirements: []
              role: "setup|fact|emotion|contrast|aftertaste|silent"
              must_not_caption_visible_content: true
            p800_video:
              motion_requirements: []
              start_state: ""
              last_frame_or_end_state: ""
              must_not_add: []
            carries_to_next_cut: []
            carries_to_next_scene: []
          event_context_for_cut:
            derived_from: "scene_event.event_sequence + cut_contract.source_event_contract"
            editable: false
            primary_event_beat:
              beat_id: "scene1_event_setup"
              beat_function: "setup"
            neighboring_event_beats: []
            forbidden_event_changes: []
            reveal_constraints_for_this_cut:
              allowed_reveal_info_ids: []
              forbidden_reveal_info_ids: []
        legacy_scene_contract_alias:
          cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
          target_beat: "この cut で伝える1つのこと"
          screen_question: "観客が画面から読む問い"
          dramatic_job: "scene全体のどこを担当するか"
          audience_knowledge_delta: "<cut_contract.viewer_contract.audience_knowledge_delta>"
          causal_proof: "<cut_contract.viewer_contract.causal_proof>"
          visual_evidence: "<cut_contract.viewer_contract.visual_evidence>"
          required_roles: "<cut_contract.viewer_contract.required_roles>"
          source_event_contract: "<cut_contract.source_event_contract>"
          anti_redundancy_key: "<cut_contract.viewer_contract.anti_redundancy_key>"
          visual_beat: "画として何が見えるか"
          first_frame_brief: "動画が動き出す直前に見えている初期状態。prompt本文に制作メタは入れない"
          static_first_frame_rule: "<cut_contract.first_frame_contract.static_first_frame_rule>"
          motion_brief: "p800 motion prompt 専用。p600 image prompt authoring では参照しない"
          must_show: []
          must_avoid: []
          done_when: []
        scene_contract:
          legacy_note: "旧runtime向け cut-level alias。新規設計では cut_contract を正本とする。"
          target_beat: "<cut_contract.viewer_contract.target_beat>"
          must_show: "<cut_contract.viewer_contract.must_show>"
          must_avoid: "<cut_contract.viewer_contract.must_avoid>"
          done_when: "<cut_contract.viewer_contract.done_when>"
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
            cut_function: <cut_contract.cut_function>
            camera: TODO
            subject_motion: TODO
            environment_motion: TODO
            emotional_change: TODO
            end_state: TODO
            avoid: 新キャラ追加、重要道具の追加、reveal早出し、画面内テキスト、過剰なズーム。
          output: "assets/scenes/scene1_cut1_video.mp4"
        audio:
          narration:
            authoring_status: "missing|draft|approved|silent"
            missing_reason: "p700_narration_not_written_yet"
            contract:
              schema_version: "narration_contract_v2"
              story_role:
                narrative_position: "opening|middle|ending"
                cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
                voice_function: "information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence"
              visual_distance:
                distance_policy: "stay_close|contextual|meaning_first|silent"
                narration_should_add: []
              tts_readiness:
                pronunciation_targets: []
              # compatibility alias
              role: "setup|fact|emotion|contrast|aftertaste|silent"
              target_function: "derive_from_story_role_voice_function"
              must_cover:
                - "derive_from_story_role_must_cover"
              must_avoid:
                - "映像のキャプション化"
              done_when:
                - "derive_from_story_role_done_when"
            draft:
              text: ""
              status: "optional_draft|approved_by_human|superseded_by_p700"
            text: ""
            tts_text: ""
            tool: "elevenlabs"
            review:
              agent_review_ok: false
              agent_review_reason_keys: []
              agent_review_reason_messages: []
              pronunciation_review:
                candidates: []
                unresolved: []
              narration_arc_review:
                agent_review_ok: false
                reason_keys: []
                rubric_scores: {}
              human_review_ok: false
              human_review_reason: ""
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
