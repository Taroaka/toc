# Requirements

## Goal

画像生成 prompt の構造化を repo-wide の必須要件として明文化し、subagent review が required block 欠落を false として扱うように docs/spec を揃える。

## Requirements

- 対象は特定フローではなく repo 全体の image prompt contract とする
- prompt は次の 6 block を必須とする
  - `[全体 / 不変条件]`
  - `[登場人物]`
  - `[小道具 / 舞台装置]`
  - `[シーン]`
  - `[連続性]`
  - `[禁止]`
- 上記 block のいずれかが欠けている prompt entry は subagent review が `agent_review_ok: false` にする
- 欠落時は false reason key を残す
- required block 欠落は prompt の質の好みではなく、設計違反として扱う
- docs / templates / steering のみ更新し、runtime 実装は変更しない
