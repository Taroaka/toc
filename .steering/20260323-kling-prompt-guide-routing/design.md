# Design

## Decision

- Kling 専用 guide は新規ファイルではなく `workflow/playbooks/video-generation/kling.md` を昇格させる
- 汎用原則は `docs/video-generation.md` に残し、Kling 特有の prompt 構造・運用ルール・例だけを playbook 側へ置く
- 参照分岐は「tool 名」で決める
  - `kling_3_0`
  - `kling_3_0_omni`

## Why This Shape

- selector / playbook の既存構造に乗るため、agent が「どの動画生成方式か」を説明しやすい
- vendor docs (`docs/vendor/kling/`) は API / 課金 / integration 情報が中心で、prompt writing の正本には向かない
- 既存の `kling.md` を整理すれば、参照 path を増やさずに済む

## Changes

### 1. Kling guide の再構成

- `workflow/playbooks/video-generation/kling.md` を以下の章構成へ置き換える
  - 目的と適用範囲
  - ToC での使いどころ
  - prompt の基本構造
  - Kling 向け運用原則
  - text-to-video / image-to-video の書き分け
  - motion / continuity / negative prompt の扱い
  - 良い例 / 悪い例
  - agent 向け参照ルール

### 2. Story / Script docs への導線追加

- `docs/story-creation.md` に、物語から下流 prompt 要件を逆算する際の provider-specific reference を追記する
- `docs/script-creation.md` に、Kling 指定時は `docs/video-generation.md` ではなく `workflow/playbooks/video-generation/kling.md` を優先して prompt を具体化するルールを追記する

### 3. Agent docs / prompts の明文化

- `docs/implementation/agent-roles-and-prompts.md` に、Scriptwriter 系 agent の Kling 分岐を追記する
- `.claude/agents/immersive-scriptwriter.md` に、`video_generation.tool` が Kling 系なら専用 guide を優先参照する指示を追記する

## Verification

- 変更ファイルの参照整合を目視確認する
- `rg` で Kling guide への導線が追加されたことを確認する
