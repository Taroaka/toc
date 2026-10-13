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

## 作者の意図から考える

`docs/story-creation.md` の「何を届けたいかからシーンを考える」を思考の手がかりにする。
「ここで何をしたいか」「観客に何を届けたいか」が先であり、起承転結や導入・反応・余韻は
そのために選べる方法である。四つの機能を全sceneにそろえたり、毎sceneに回答を義務付けたりしない。
意図が伝わらない原因が場所や人物の説明不足なら手がかりを補い、沈黙・省略・唐突さが
意図に合うならそのまま使える。必要な判断を既存のscene_intent/direction等へ文章で残し、
形式のために出来事や必須項目を増やさない。既存の採用映像・音声は依頼なく再生成しない。

storyは後段の撮影方法を固定する場所ではありません。manifest cutの任意のshot分割を設計するときは、意図から人物の目的・感情、必要な可視範囲、動きの時間とカメラを選ぶ順序をリポジトリの `docs/implementation/shot-direction.md`で確認し、全scene共通のshot数や表情を課さないでください。
