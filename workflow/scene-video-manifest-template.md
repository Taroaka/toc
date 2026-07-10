# scene単体: 動画マニフェストテンプレ（改善版）

このテンプレは `output/<topic>_<timestamp>/scenes/sceneXX/video_manifest.md` 用。
scene 単体 run でも、p400 の cinematic scene contract → p600 `first_frame_visual_plan -> drawable_prompt_ir -> api_prompt_payload` → p800 motion の責務を崩さない。
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

image_request_materialization:
  prompt_policy_version: "image_api_prompt_v2"
  compiler_version: "conditional_drawable_prompt_compiler_v1"
  review_projection: "image_generation_requests.md"
  review_prompt_fence: "api_prompt"
  execution_snapshot: "image_generation_request_snapshot.json"
  snapshot_schema_version: "toc.image_generation_request_snapshot.v1"
  provider_prompt_path: "snapshot.items[].prompt"
  provider_prompt_source: "scenes[].cuts[].image_generation.api_prompt_payload.prompt"
  immutable_after_materialization: true
  reject_markdown_or_reference_drift: true
  unique_destination_owner_per_snapshot: true
  reject_cross_revision_output: true
  legacy_v1_compatibility: "image_generation.prompt は read-only。v2 failure 時に暗黙 fallback しない"

assets:
  character_bible:
    - character_id: "protagonist"
      reference_images: []
      reference_variants: []
      fixed_prompts:
        - "黒髪の短髪、和装の実写的な布地"
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
  location_bible:
    - location_id: "village_at_dawn"
      reference_images: []
      reference_variants: []
      fixed_prompts:
        - "夜明けの木造家屋、湿った土の道、低い朝霧"

human_change_requests: []

scene_generation:
  schema_version: "scene_generation_policy_v1"
  canonical_payload_path: "scenes[].scene_generation.scene_prompt_payload.prompt"
  deprecated_fields: ["scene_generation.prompt"]
  required_blocks: ["scene_authoring_context", "scene_prompt_payload", "scene_debug_prompt_source", "scene_generation_contract"]
  required_outputs: ["scene_intent", "scene_event", "scene_character_state_timeline", "scene_film_coverage_plan", "scene_cut_coverage_plan", "forbidden_event_changes"]
  downstream_boundary: "cut/image/narration/video は scene_prompt_payload を読まず、scene_event と scene_cut_coverage_plan から逆算する"

canonical_event_coverage_matrix:
  policy_version: "canonical_event_coverage_matrix_v1"
  source: ["parent_story", "scene_script", "asset_bible"]
  source_story_events:
    - source_event_id: ""
      source_event_summary: ""
      importance: "low|medium|high|critical"
      required: true
      must_appear_as: "scene|cut|narration|visual_motif|can_be_omitted"
      canonical_order_index: 0
      assigned_scene_ids: []
      assigned_event_beat_ids: []
      omission_reason: ""
      adaptation_change_reason: ""
      human_approval_required: false

scenes:
  - scene_id: 1
    timestamp: "00:00-00:30"
    importance: "medium"
    target_duration_seconds: 30
    estimated_duration_seconds: 30
    handoff_to_next_scene: "terminal_resolution または次sceneへのアンカー"
    terminal_resolution: ""
    # scene_generation は scene 正本を作る authoring prompt の正本。
    # scene_prompt_payload.prompt には first-frame / motion / API prompt / camera / lens / framing / shot / 固定cut数を混ぜない。
    scene_generation:
      schema_version: "scene_generation_v1"
      scene_authoring_context:
        schema_version: "scene_authoring_context_v1"
        topic: "<topic>"
        scene_id: 1
        scene_index: 1
        scene_title: ""
        story_scope: {}
        source_beats: []
        canonical_event_policy:
          source_story_events: "top-level canonical_event_coverage_matrix を参照"
          scene_specificity: "source beat を scene_event の具体出来事へ接地する"
        scene_count_policy:
          maximize_meaningful_scene_count: true
          do_not_fix_cut_count_in_prompt: true
          cut_count_is_derived_by: "scene_cut_coverage_plan"
      scene_prompt_payload:
        schema_version: "scene_prompt_payload_v1"
        prompt: "この scene が物語内で何を成立させるかを設計し、scene 正本を出力する。後段実行情報は含めない。"
        input_refs: ["story.md", "research.md", "visual_value.md", "canonical_event_coverage_matrix", "asset_bible"]
        required_outputs: ["scene_intent", "scene_event", "scene_character_state_timeline", "scene_film_coverage_plan", "scene_cut_coverage_plan", "forbidden_event_changes"]
        constraints: ["scene 正本生成だけに使う", "後段の画像・音声・動画実行情報を含めない", "scene_event は物語事実に限定する"]
      scene_debug_prompt_source:
        schema_version: "scene_debug_prompt_source_v1"
        not_sent_to_agent: true
        source_story_beat_ids: []
        source_beats: []
        source_origin: "user_input|script|canonical_reference|asset_bible|inferred|adaptation_choice"
        adaptation_choices: []
        excluded_from_payload: []
        forbidden_event_changes_source: "scene_event.forbidden_event_changes"
      scene_generation_contract:
        schema_version: "scene_generation_contract_v1"
        required_outputs: ["scene_intent", "scene_event", "scene_character_state_timeline", "scene_film_coverage_plan", "scene_cut_coverage_plan", "forbidden_event_changes"]
        scene_event_schema_version: "scene_event_v1"
        payload_boundary: "scene_prompt_payload は scene 正本生成だけに使う"
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
            source_concrete_events: []
            source_story_grounding: []
            source_non_replaceable_elements: []
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
            mixed_affect_design:
              mode: "none|single|mixed|tension_release|bittersweet|aftertaste"
              optional: true
              apply_when: []
              positive_valence_thread: ""
              negative_valence_thread: ""
              arousal_strategy: "hold|rise|drop|spike|release"
              audience_rollercoaster_job: "none|bond|strain|release|reframe|aftertaste"
              design_intent: ""
              visible_support: []
              narration_support: []
              sound_or_rhythm_support: []
              handoff_effect: ""
              avoid_if:
                - "1 cut = 1意図 を壊す"
                - "scene_event にない事実を足す"
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
              authoring_boundary: "cut設計では完成 prompt を書かず、描画可能な first-frame 要件だけを渡す"
              source_projection: "first_frame_visual_plan_v1"
              compiler_flow: "first_frame_visual_plan -> drawable_prompt_ir -> api_prompt_payload"
              prompt_policy_version: "image_api_prompt_v2"
              compiler_version: "conditional_drawable_prompt_compiler_v1"
              drawable_prompt_ir_schema_version: "drawable_prompt_ir_v1"
              always_required_groups: ["style", "current_moment", "primary_subject", "composition", "constraints"]
              conditional_groups:
                references: "resolved references が1件以上ある場合だけ"
                characters: "asset_dependency.character_ids_required が1件以上ある場合だけ"
                objects: "asset_dependency.object_ids_required が1件以上ある場合だけ"
                location: "asset_dependency.location_ids_required が1件以上ある場合だけ"
                light_material: "明示された非定型の描画値がある場合だけ"
                current_state_delta: "sequential progression の明示された描画値がある場合だけ"
              prompt_requirements: []
              reference_requirements: []
              first_frame_must_include: []
              first_frame_must_avoid: []
              provider_prompt_path: "image_generation.api_prompt_payload.prompt"
              review_projection: "image_generation_requests.md#api_prompt"
              execution_snapshot: "image_generation_request_snapshot.json"
              legacy_v1_compatibility: "image_generation.prompt は read-only。v2 failure 時に暗黙 fallback しない"
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
          # provider へ渡す本文は api_prompt_payload.prompt だけ。
          # first_frame_visual_plan / drawable_prompt_ir / ID / path / hash / motion_brief は prompt 本文へ出さない。
          tool: "codex_builtin_image"
          character_ids: ["protagonist"]
          character_variant_ids: []
          object_ids: []
          object_variant_ids: []
          location_ids: ["village_at_dawn"]
          location_variant_ids: []
          references: []
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
          # IDs / references / first_frame_visual_plan が変わったら、IR/payload/hash/snapshot を一括再生成する。
          first_frame_visual_plan:
            schema_version: "first_frame_visual_plan_v1"
            editable: false
            temporal_boundary:
              first_visible_moment: "夜明けの村で主人公が湿った土の道の先を見つめている"
              event_fact_visible_in_still: "主人公はまだ歩き出していない"
              not_yet_happened_in_still: ["主人公が村を出る"]
            subject_binding:
              primary_subject:
                name: "道の先を見つめる主人公"
            spatial_composition:
              foreground: "霧に濡れた土の道"
              midground: "立ち止まる主人公"
              background: "木造家屋と遠い山の輪郭"
            prompt_rendering_policy:
              render_only_drawable_information: true
              do_not_render_design_meta: true
              do_not_render_future_motion_as_action: true
          api_prompt_payload:
            policy_version: "image_api_prompt_v2"
            compiler_version: "conditional_drawable_prompt_compiler_v1"
            prompt: |-
              [全体 / 不変条件]
              実写映画調、自然な映画照明、実物セットとして見える質感。

              [シーン]
              画面には、主人公はまだ歩き出していない。
              観客が最初に読む主被写体は、道の先を見つめる主人公。

              [登場人物]
              人物の姿勢と状態は、主人公はまだ歩き出していないとして明確に見える。

              [場所と構図]
              場所は、前景に霧に濡れた土の道、中景に立ち止まる主人公、背景に木造家屋と遠い山の輪郭。
              道の先を見つめる主人公が最初に読める構図。

              [禁止]
              画面内テキスト、字幕、ロゴ、ウォーターマーク、アニメ、漫画、イラストを入れない。
              まだ描かないものは、主人公が村を出る。
            negative_prompt: "画面内テキスト、字幕、ロゴ、ウォーターマーク、アニメ、漫画、イラスト"
            reference_instructions: ""
            reference_images: []
            sha256: "<sha256-of-exact-prompt>"
            source_digest: "<sha256-of-first-frame-compilation-source>"
            drawable_prompt_ir:
              schema_version: "drawable_prompt_ir_v1"
              dependencies:
                character_ids: ["protagonist"]
                object_ids: []
                location_ids: ["village_at_dawn"]
                references: []
                required_groups: ["style", "current_moment", "primary_subject", "characters", "location", "composition", "constraints"]
              included_fragments:
                - group: "style"
                  text: "実写映画調、自然な映画照明、実物セットとして見える質感。"
                - group: "current_moment"
                  text: "画面には、主人公はまだ歩き出していない。"
                - group: "primary_subject"
                  text: "観客が最初に読む主被写体は、道の先を見つめる主人公。"
                - group: "characters"
                  text: "人物の姿勢と状態は、主人公はまだ歩き出していないとして明確に見える。"
                - group: "location"
                  text: "場所は、前景に霧に濡れた土の道、中景に立ち止まる主人公、背景に木造家屋と遠い山の輪郭。"
                - group: "composition"
                  text: "道の先を見つめる主人公が最初に読める構図。"
                - group: "constraints"
                  text: "画面内テキスト、字幕、ロゴ、ウォーターマーク、アニメ、漫画、イラストを入れない。\nまだ描かないものは、主人公が村を出る。"
              omitted_groups: ["references", "objects", "light_material", "current_state_delta"]
          prompt: ""  # image_api_prompt_v1 legacy read-only projection。production v2 の送信には使わない
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
