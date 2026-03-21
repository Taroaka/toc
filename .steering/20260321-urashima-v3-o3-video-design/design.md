# Design: Urashima V3/O3 video design

## Clip promotion rule

- Promote every `generate_still` cut to a video clip.
- Promote only a small set of `no_dedicated_still` cuts when they carry a major spatial or emotional transition.
- Keep `reuse_anchor` cuts outside the standalone clip list by default; they ride inside adjacent clip motion or narration time.

## Duration rule

- Silent Ryugu spectacle cuts stay at `4s`.
- Standard promoted anchor cuts use provisional `5s`.
- Promoted bridge cuts use provisional `4s`.

This keeps the design near the story target length without forcing every narration cut into its own paid clip.

## Model split

- `kling_3_0` for standard clips.
- `kling_3_0_omni` for high-difficulty or high-value clips:
  - palace reveal
  - central Ryugu spectacle
  - tamatebako handoff
  - smoke engulf / aging transition
  - aged-face reveal

## Planning artifact

- Write a run-level `video_generation_plan.md` with:
  - selected cuts
  - tool split (V3 vs O3)
  - billed/provisional duration totals
