# 動画マニフェスト: テンプレート（改善版）

`docs/video-generation.md` の出力スキーマに準拠した作業テンプレートです。
改善版では、scene を映画的な劇的単位として扱い、`scene_intent` → `scene_event` → `scene_cut_coverage_plan` → `cut_contract.source_event_contract` → `event_context_for_cut` → `image_generation.prompt` / `narration` / `video_generation.motion_prompt` のつながりを明示します。
このテンプレートは skeleton 作成にも使うため、image/video authoring prompt には TODO を含むことがある。ただし `audio.narration.text` / `audio.narration.tts_text` には TODO を入れず、未記入は空文字 + `authoring_status` で表す。`manifest_phase: production` へ昇格する時点では TODO / TBD / pending を残さない。

- 出力先: `output/videos/<topic>_<timestamp>_manifest.md`
  - 1物語1フォルダ運用の場合: `output/<topic>_<timestamp>/video_manifest.md`
- 目的: 生成素材・選定・合成の管理
- 原則: p400 では完成 image prompt を書かず、p600 で 6 block prompt を作る

```yaml
manifest_phase: "skeleton"

# === メタ情報 ===
video_metadata:
  topic: "<topic>"
  source_story: "output/<topic>_<timestamp>/story.md"
  source_script: "output/<topic>_<timestamp>/script.md"
  source_visual_value: "output/<topic>_<timestamp>/visual_value.md"
  created_at: "<ISO8601>"
  target_duration_seconds: 300
  estimated_duration_seconds: 300
  duration_seconds: 300  # compatibility alias
  experience: "cinematic_story"
  aspect_ratio: "9:16"
  resolution: "1080x1920"

promotion_requirements:
  no_todo_or_tbd: true
  all_cut_contracts_complete: true
  all_image_prompts_approved: true
  all_narration_text_finalized_or_silent: true
  all_video_motion_prompts_complete: true

subagent_trace:
  - subagent_id: "image-prompt-judgment-001"
    role: "scene_review|cut_blueprint_review|narration_review|duration_stretch_review|asset_continuity_review|image_prompt_judgment|clip_review|qa_review"
    input_artifact: "output/<topic>_<timestamp>/video_manifest.md"
    output_artifact: "output/<topic>_<timestamp>/logs/review/image_prompt.judgment.md"
    accepted_by_main: false
    reason: "string"

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
          - "scene をまたいでも身長感と骨格を変えない"
      relative_scale_rules:
        - "他キャラクターと同フレームにいるときも、主人公の体格を scene 間で変えない"
      reference_variants: []
      fixed_prompts:
        - "黒髪の短髪"
        - "和装（実写的な生地感）"
      cinematic:
        role: "観客が感情移入する中心人物"
        continuity_risks:
          - "顔・年齢感・衣装・体格の drift"

  style_guide:
    visual_style: "実写映画調、自然な映画照明、実物セット感"
    reference_images:
      - "assets/styles/reference_1.png"
    forbidden:
      - "画面内テキスト"
      - "字幕"
      - "ウォーターマーク"
      - "ロゴ"
      - "アニメ/漫画/イラスト調"

  object_bible: []
  # - object_id: "tamatebako"
  #   kind: "artifact"  # setpiece|artifact|phenomenon
  #   reference_images:
  #     - "assets/objects/tamatebako_closeup.png"
  #   fixed_prompts:
  #     - "箱の材質/構造の不変条件"
  #     - "文字で説明せず、形/光/動きで魅力と危うさを伝える"
  #   cinematic:
  #     role: "贈与 + 禁忌 + 代償"
  #     scene_usage:
  #       first_appearance: "scene05_cut02"
  #       reveal_stage: "hinted|featured|transformed|aftermath"
  #       pressure_function: "開けたい誘惑を作る"
  #       payoff_function: "代償の発生を視覚化する"
  #     visual_takeaways:
  #       - "開けたくなるが、開けると何かが起こる"
  #     spectacle_details:
  #       - "封印が呼吸するように発光する"

  location_bible: []
  # - location_id: "sea_temple"
  #   reference_images:
  #     - "assets/locations/sea_temple.png"
  #   reference_variants: []
  #   fixed_prompts:
  #     - "海底神殿の主要構造、祭壇、入口、光環境を固定"
  #   review_aliases: ["海底神殿"]
  #   continuity_notes:
  #     - "後続 cut でも同じ祭壇配置を維持する"
  #   notes: ""

# === 人間修正要求 ===
human_change_requests: []

# === シーン別素材 ===
scenes:
  - scene_id: 1   # dotted numeric string も可: 3.1
    timestamp: "00:00-00:24"
    importance: "medium"
    target_duration_seconds: 24
    estimated_duration_seconds: 24
    handoff_to_next_scene: "次sceneへの視覚/音/因果アンカー。最終sceneはterminal_resolution"
    terminal_resolution: ""
    scene_intent:
      importance: "medium"  # low|medium|high|critical
      target_duration_seconds: 24
      estimated_duration_seconds: 24
      story_purpose: "この scene が物語全体で担う役割"
      dramatic_question: "この scene の間、観客が追う問い"
      scene_spine: "setup → pressure → turn → payoff → handoff の1文要約"
      value_shift:
        from: "scene開始時の状態"
        to: "scene終了時の状態"
        visible_evidence:
          - "画面だけで変化が読める証拠"
      causal_turn: "次sceneを発生させる不可逆の出来事/決断/発見"
      audience_information: []
      withheld_information: []
      reveal_constraints: []
      affect_transition: "観客感情の変化"
      character_state:
        start: ""
        end: ""
        visible_behavior: []
      visual_value_source: ""
      visual_thesis: "この scene を代表する映画的な一枚絵"
      story_specificity:
        non_compressible_beat: ""
        scene_promotion_reason: ""
        unique_scene_responsibility: ""
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
      spatial_plan:
        location_id: ""
        screen_geography: "前景/中景/背景、入口/出口、進行方向"
        continuity_anchors: []
      production_risks: []
      handoff_to_next_scene: "次sceneへの視覚/音/因果アンカー。最終sceneはterminal_resolution"
      coverage_review:
        audience_information_covered: false
        visualizable_action_covered: false
        value_shift_visible: false
        causal_turn_visible: false
        scene_specificity_gate_passed: false
        next_scene_connection_checked: false
      handoff_notes:
        p500_asset: []
        p600_image: []
        p700_narration: []
        p800_video: []

    implementation_trace:
      source_request_ids: []
      status: "implemented|verified|waived"
      notes: ""

    # カット設計ルール:
    # - 1カット = 1意図。
    # - 1カット = 1ナレーション、または明示された silent cut。
    # - cut 数は固定テンプレートではなく scene_cut_coverage_plan で scene obligation から逆算する。
    # - low/medium/high/critical の重要度 floor と target_duration_seconds / 8 の duration floor を下回らない。
    # - 同じ story fact の繰り返しなら cut 追加ではなく既存 cut の prompt/contract を厚くする。
    # - cut_contract が正本。scene_contract は既存 reader 向け互換 alias。
    scene_cut_coverage_plan:
      coverage_strategy: "reverse_from_scene_event"
      source_schema_version: "scene_event_v1"
      min_cut_count:
        by_importance: 3
        by_duration: 3
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
        cut_role: "main"  # main|sub|transition|reaction|visual_payoff
        cut_status: "active|deleted"
        deletion_reason: ""
        implementation_trace:
          source_request_ids: []
          status: "implemented|verified|waived"
          notes: ""
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
            secondary_intents_allowed: []
            forbidden_combined_intents:
              - "new_location_establishing + major_reveal + next_scene_handoff"
            assigned_obligation_ids: []
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
            target_function: "この声が cut で果たす役割"
            must_cover:
              - "derive_from_story_role_must_cover"
            must_avoid:
              - "映像のキャプション化"
            timing_intent: ""
            silence_reason: ""
            draft:
              text: ""
              status: "optional_draft|approved_by_human|superseded_by_p700"
          rhythm_contract:
            expected_duration_seconds: 8
            pacing: "quick|standard|slow_hold|spectacle_hold"
            comprehension_moment: ""
            cut_out_reason: ""
            audio_visual_sync_point: ""
            duration_exception:
              allowed: false
              reason: ""
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
        scene_contract:
          legacy_note: "旧runtime向け cut-level alias。新規設計では cut_contract を正本とする。"
          cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
          target_beat: "この cut で伝える1つのこと"
          screen_question: "この cut の間、観客が画面から読む問い"
          dramatic_job: "scene全体の pressure / turn / payoff のどこを担当するか"
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
          must_show:
            - "image prompt / motion / narration のどこかで必ず見せる"
          must_avoid:
            - "この cut に入れてはいけない drift / reveal 破り / 説明過多"
          done_when:
            - "reviewer が完了判断できる条件"

        image_generation:
          # p600 image provider は codex_builtin_image 固定。
          # prompt 本文には `最初の1フレーム` / `1フレーム目` / `first frame` と書かない。
          tool: "codex_builtin_image"
          character_ids: ["protagonist"]  # 人物が映らない場合は []
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
          human_review:
            status: "pending|approved|changes_requested"
            notes: ""
            change_requests: []
          prompt: |
            [全体 / 不変条件]
            実写映画調、自然な映画照明、実物セット感。画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

            [登場人物]
            主人公は character_bible の参照画像と同じ人物。黒髪の短髪、和装の実写的な布地、体格と年齢感を維持する。

            [小道具 / 舞台装置]
            この場面で主役級の小道具はない。場所アンカーとして、夜明けの村の木造家屋、湿った土の道、低い朝霧を保つ。

            [シーン]
            舞台: 夜明けの静かな田舎の村。
            主役: 中景に立つ主人公。まだ歩き出しておらず、村の奥へ向かう視線だけが先に伸びている。
            前景: 霧に濡れた土の道と小さな草。画面下に奥へ続く導線を作る。
            中景: 主人公の姿勢と視線。これから物語が始まる直前の静けさ。
            背景: 木造家屋の影、薄い朝霧、遠くの山の輪郭。
            光: 青灰色の朝光が右奥から差し、人物の輪郭に弱いリムライトを作る。
            構図: 縦型9:16、道を中央の導線にし、人物は中景のやや下に置く。

            [連続性]
            この画像だけで、主人公がまだ日常の村にいること、次に村の奥へ進むこと、夜明けの時間帯が読める。

            [禁止]
            画面内テキスト、字幕、ウォーターマーク、ロゴ、アニメ調、漫画調、イラスト調、人物や手の崩れ、余計な人物、reveal早出し。
          output: "assets/scenes/scene1_cut1_base.png"
          iterations: 4
          selected: null

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
              tool: "codex_builtin_image"
              character_ids: ["protagonist"]
              object_ids: []
              location_ids: []
              prompt: "same as primary image prompt"
              output: "assets/scenes/scene1_cut1_base.png"

        video_generation:
          tool: "kling_3_0"
          duration_seconds: 8
          input_image: "assets/scenes/scene1_cut1_base.png"
          input_asset_id: "scene1_cut1_base"
          first_frame_asset_id: ""
          last_frame_asset_id: ""
          reference_asset_ids: []
          direction_notes: []
          continuity_notes: []
          applied_request_ids: []
          motion_prompt: |
            cut_function: <cut_contract.cut_function>
            camera: 静止画の構図を保ち、ゆっくり奥へ進む。過剰なズームはしない。
            subject_motion: 主人公はまだ大きく動かず、視線とわずかな体重移動だけで次の行動を予感させる。
            environment_motion: 朝霧が低く流れ、草が小さく揺れる。
            emotional_change: 静かな日常から、物語が始まる前の期待へ移る。
            end_state: 主人公の視線が村の奥へ残り、次 cut へ進む方向が明確になる。
            avoid: 新キャラ追加、重要道具の追加、reveal早出し、画面内テキスト、過剰ズーム、アニメ調。
          output: "assets/scenes/scene1_cut1_video.mp4"

        audio:
          narration:
            authoring_status: "missing|draft|approved|silent"
            missing_reason: "p700_narration_not_written_yet"
            contract:
              schema_version: "narration_contract_v2"
              story_role:
                narrative_position: "opening"
                cut_function: "setup"
                voice_function: "information"
                audience_state_before: ""
                audience_state_after: ""
                must_cover: []
                must_not_reveal: []
                done_when:
                  - "物語の導入として自然に読める"
                  - "映像で読めることを説明しすぎない"
              visual_distance:
                distance_policy: "stay_close"
                visible_facts_in_frame: []
                narration_should_add: []
                must_not_caption_visible_action: true
                visual_overlap_allowed: true
                visual_overlap_reason: "opening の導入で場所認知を安定させるため"
              rhythm_and_timing:
                target_speech_seconds: 0
                min_speech_seconds: 0
                max_speech_seconds: 0
                start_timing: "after_visual_read"
                end_timing: "on_cut_end"
                pause_intent: []
                audio_visual_sync_point: ""
              tts_readiness:
                normalization_policy: "kanji_public_hiragana_tts"
                pronunciation_targets: []
                max_sentence_chars: 42
                tts_text_must_differ_from_text_when_needed: true
              # compatibility aliases for older readers
              role: "setup"
              target_function: "information"
              must_cover:
                - "derive_from_story_role_must_cover"
              must_avoid: ["カメラ", "ズーム", "生成", "prompt"]
              done_when:
                - "物語の導入として自然に読める"
                - "映像で読めることを説明しすぎない"
            text: ""
            tts_text: ""
            tool: "elevenlabs|silent"
            silence_contract:
              intentional: false
              kind: "visual_value_hold|transition_hold|reaction_hold|tension_hold|breathing_room|ending_aftertaste|none|other"
              confirmed_by_human: false
              reason: ""
              expected_viewer_effect: ""
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
            human_review:
              status: "pending|approved|changes_requested"
              notes: ""
              change_requests: []
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
    must_avoid: []
    done_when: []
  scene_value_shift_visible: false
  causal_turn_visible: false
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
