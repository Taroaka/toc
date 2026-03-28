# Requirements

## Goal

画像生成に入る前に、prompt が story/script と整合し、不足 `character_ids` を補完できる review gate を設ける。人間が確認した run は、残 finding があっても例外的に進行できる。

## Requirements

- `review-image-prompt-story-consistency.py` は missing character だけでなく、prompt drift と blocking drift、必須 6 ブロック `[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`, `[連続性]`, `[禁止]` の欠落を検出する
- review gate は prompt の独立性も検査し、他 cut 参照や前後 prompt 依存、`rideable` のような英語 shorthand を false にする
- review は不足 `character_ids` を自動補完できる
- prompt collection に subagent / human review の状態と false 理由を持てる
- `generate-assets-from-manifest.py` は画像生成前に review を通す
- subagent が直した後に再 review して true に戻せる
- `agent_review_ok=false` でも、人間が対象 cut を許容した場合だけ bypass できる
