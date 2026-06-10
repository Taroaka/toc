# シーン台本テンプレ（Cinematic Scene Script）

p400 / scene-series 用の最小台本テンプレ。
Q&A短尺にも使えるが、scene は「答えを説明する段落」ではなく、観客の理解・感情・期待が変化する劇的単位として設計する。

```yaml
scene_script_metadata:
  topic: "<topic>"
  scene_id: <scene_id>
  source_story: "output/<topic>_<timestamp>/story.md"
  source_research: "output/<topic>_<timestamp>/research.md"
  target_seconds: 30
  aspect_ratio: "9:16"
  created_at: "<ISO8601>"

scene_intent:
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
  handoff_to_next_scene: "次 scene への視覚/音/因果アンカー"

# ナレーションは image prompt の主ソースではない。
# 映像で見せるものと、声で補うものを分ける。
narration_plan:
  voice_distance: "close|neutral|observational|minimal"
  must_cover: []
  must_avoid: []
  full_text: "<scene全体のナレーション。cutごとに分割する前の案>"

cuts:
  - cut_id: 1
    cut_role: "main|sub|transition|reaction|visual_payoff"
    cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
    target_seconds: 8
    target_beat: "この cut で伝える1つのこと"
    screen_question: "観客が画面から読む問い"
    visual_beat: "画として何が見えるか"
    first_frame_brief: "動画が動き出す直前に見えている初期状態。prompt本文に制作メタは入れない"
    motion_brief: "p800 motion prompt 専用。p600 image prompt authoring では参照しない"
    narrative_position: "opening|middle|ending"
    voice_function: "information|emotion|causality|time|viewpoint|world_rule|contrast|meaning|aftertaste|silence"
    visual_distance_policy: "stay_close|contextual|meaning_first|silent"
    pronunciation_targets: []
    narration_role: "setup|fact|emotion|contrast|aftertaste|silent"
    narration_text: "<このcutのナレーション。silentなら空文字>"
    must_show: []
    must_avoid: []
    done_when: []
    asset_dependency_hint:
      character_ids: []
      object_ids: []
      location_ids: []

text_overlay:
  main_text: "<必要な場合のみ。映像内の看板や刻印とは別物>"
  sub_text: "<必要な場合のみ>"

quality_check:
  scene_has_value_shift: false
  scene_has_causal_turn: false
  cut_count_sufficient: false
  visualizable_without_narration: false
  reveal_order_preserved: false
  notes: []
```
