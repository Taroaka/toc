# Design: Mixed Affect Cut Design

## Approach

既存の `viewer_contract.emotional_micro_shift` を置き換えず、その下に optional な `mixed_affect_design` を追加する。

`mixed_affect_design` は、単なる感情ラベルではなく「正負感情の同時性または短時間の交替を、この cut がどう支えるか」を表す。採用しない cut は `mode: "none"` とし、理由を残す。

## Contract Shape

```yaml
viewer_contract:
  emotional_micro_shift:
    from: ""
    to: ""
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
    avoid_if: []
```

## Rules

- `mode: none` is valid and should be used when the cut's job is pure information, continuity, or a simple setup.
- Use mixed affect only when it strengthens the scene's causal or emotional job.
- A mixed affect cut still has one primary viewer-facing intent. The mixed layer is support, not a second plot beat.
- If adopted, at least one support path should be concrete: visible behavior, narration, sound/rhythm, or cut handoff.
- Do not invent new factual claims to create emotion.

## Integration

- Docs define the semantics and review expectations.
- Templates expose the field to future artifacts.
- `scripts/toc-immersive-frontend-run.py` seeds the field using cut function: pressure/turn/payoff/terminal cuts are more likely to use it; setup/handoff may remain `none`.
