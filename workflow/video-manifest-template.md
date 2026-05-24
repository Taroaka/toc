# 動画マニフェスト: テンプレート（改善版）

`docs/video-generation.md` の出力スキーマに準拠した作業テンプレートです。
改善版では、scene を映画的な劇的単位として扱い、`scene_intent` → `scene_contract` → `image_generation.prompt` → `video_generation.motion_prompt` のつながりを明示します。

- 出力先: `output/videos/<topic>_<timestamp>_manifest.md`
  - 1物語1フォルダ運用の場合: `output/<topic>_<timestamp>/video_manifest.md`
- 目的: 生成素材・選定・合成の管理
- 原則: p400 では完成 image prompt を書かず、p600 で 6 block prompt を作る

```yaml
manifest_phase: "skeleton|production"

# === メタ情報 ===
video_metadata:
  topic: "<topic>"
  source_story: "output/<topic>_<timestamp>/story.md"
  source_script: "output/<topic>_<timestamp>/script.md"
  source_visual_value: "output/<topic>_<timestamp>/visual_value.md"
  created_at: "<ISO8601>"
  duration_seconds: 60
  aspect_ratio: "9:16"
  resolution: "1080x1920"

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
    # - cinematic_story の production scene は原則3カット以上。low importance は2カット以上、high/critical は5カット以上。
    # - target_duration_seconds / 8 を切り上げたカット数も下回らない。
    # - cut_contract が正本。scene_contract は既存 reader 向け互換 alias。
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
          screen_question: "この cut の間、観客が画面から読む問い"
          dramatic_job: "scene全体の pressure / turn / payoff のどこを担当するか"
          visual_beat: "画として何が見えるか"
          first_frame_brief: "動画が動き出す直前に見えている初期状態。prompt本文に制作メタは入れない"
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
            cut_function: <scene_contract.cut_function>
            camera: 静止画の構図を保ち、ゆっくり奥へ進む。過剰なズームはしない。
            subject_motion: 主人公はまだ大きく動かず、視線とわずかな体重移動だけで次の行動を予感させる。
            environment_motion: 朝霧が低く流れ、草が小さく揺れる。
            emotional_change: 静かな日常から、物語が始まる前の期待へ移る。
            end_state: 主人公の視線が村の奥へ残り、次 cut へ進む方向が明確になる。
            avoid: 新キャラ追加、重要道具の追加、reveal早出し、画面内テキスト、過剰ズーム、アニメ調。
          output: "assets/scenes/scene1_cut1_video.mp4"

        audio:
          narration:
            contract:
              target_function: "opening_setup"
              must_cover: []
              must_avoid: ["カメラ", "ズーム", "生成", "prompt"]
              done_when:
                - "物語の導入として自然に読める"
                - "映像で読めることを説明しすぎない"
            text: "TODO: この cut のナレーション。silent cut の場合は空文字。"
            tts_text: "TODO"
            tool: "elevenlabs|silent"
            silence_contract:
              intentional: false
              kind: "visual_value_hold|tension_hold|none"
              confirmed_by_human: false
              reason: ""
            review:
              agent_review_ok: false
              agent_review_reason_keys: []
              agent_review_reason_messages: []
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
