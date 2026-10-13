---
name: toc-scene-design
description: >
  Run the ToC story / scene design stage with the canonical story docs and source context. Use when: turning `research.md` into `story.md` for a run directory.
---

# ToC Scene Design

1. Start with `python scripts/resolve-stage-grounding.py --stage story --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`.
2. Read the prepared source/readset and confirm the required documents and `research.md` are present before writing.
3. Read `docs/story-creation.md`, `docs/affect-design.md`, and `workflow/story-template.yaml`.
4. Write `story.md` so later script / manifest stages can trace back to `research.md`.

## シーンの入口と感情の流れ

- `docs/story-creation.md` の「シーンへの入り方と理解・感情の起承転結」を、cut分割前に読む。
- 前sceneで観客に見せたことと、今回の冒頭が前提にする場所・時間・人物・関係・到着の差を確認する。
  素材が存在するだけで登場人物を紹介済みとしない。必要なら到着・位置関係・視線・迎え等を
  既存source beat内に設計し、やり取りの途中へ突然飛び込ませない。
- 導入→期待の積み上げ→出来事/変化→反応/余韻を全編の感情の流れへ結ぶ。
  4cut、外観shot、反転、喜びを一律に要求せず、理解できる省略や意図した謎を残す。
- 判断を既存のscene_intent、start/end state、event_sequence、handoffへ反映する。
  原作外の出来事や移動手段を作らず、既存の採用映像・音声を指示なく再生成しない。
