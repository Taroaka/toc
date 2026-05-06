# Agent Roles & Prompts（正本）

このドキュメントは `.steering/20260117-agent-roles/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

役割単位で責務を分離し、再現性の高い出力と検証可能性を確保する。

## 実行モデル

- 起点は Codex 主軸の assistant command（Claude Code slash command 互換も維持）
- 統括エージェントが `state.txt` を更新
- 役割別の振る舞いはこのドキュメントと stage readset を正本にし、Claude Code 互換の agent pack は `.claude/agents/*.md` に置く（例: `director`）

## 役割と責務

### Orchestrator（統括 / single writer）
- 入力: user request / `state.txt` / `p000_index.md` / stage readset
- 出力: canonical artifact updates / state slot updates / subagent task packets
- 参照: `docs/root-pointer-guide.md` / `docs/system-architecture.md` / `workflow/stage-grounding.yaml`
- 責務:
  - stage ごとに `prepare-stage-context.py` で readset を確定する
  - `p100`-`p900` の依存順序、review policy、approval gate を管理する
  - subagent に渡す入力を artifact path / 目的 / 出力先へ限定する
  - subagent の draft / audit / review / scratch output を読み、canonical artifact へ採用する差分を選ぶ
  - authoring 直後の review slot では、最大 5 round の evaluator-improvement loop を管理する
  - 各 round で 5 critic agents と 1 aggregator agent を isolated output に限定して起動する
  - aggregator report のうち採用する修正だけを canonical artifact へ反映し、次 round / gate close / human handoff を決める
  - `state.txt` と `p000_index.md` を append / update し、stage verifier へつなぐ
- 禁止:
  - subagent に未読の親文脈を前提にさせる
  - 複数 subagent に同じ canonical file を同時編集させる
  - hybridization や human review を自動承認する
  - `state.txt` の置き換えや final status の丸投げを行う

### Director（監督）
- 入力: `research.md`
- 出力: `story.md`
- 参照: `docs/story-creation.md`
- Claude Code 互換 agent 定義: `.claude/agents/director.md`

### Visual Value Ideator
- 入力: `research.md` + `story.md`
- 出力: `visual_value.md`
- 目的: p300 visual planning の正本として、visual identity / scene visual value / anchor / reference strategy / asset bible candidates / regeneration risks / handoff を定義する
- 制約:
  - cut prompt、画像生成 request、asset 画像、動画 motion prompt は作らない
  - p400 / p600 / p700 が迷わない判断基準を `visual_value.md` に残す
  - silent visual payoff は p300 の一部機能であり、必要な run だけ `value_parts[]` に定義する
  - 文字ではなく、形 / 光 / 動き / 機構 / ショー性で伝える価値を優先する
- Claude Code 互換 agent 定義: `.claude/agents/visual-value-ideator.md`

### Scriptwriter
- 入力: `story.md` + `visual_value.md` + scene plan
- 出力: `script.md`
- 参照: `docs/script-creation.md`
- Kling 分岐: `video_generation.tool` が `kling_3_0` / `kling_3_0_omni` の場合、動画 prompt 設計は `docs/video-generation.md` の一般論ではなく `workflow/playbooks/video-generation/kling.md` を優先参照する

### Narration Writer（TTS原稿）
- 入力: `story.md` / `script.md` / `video_manifest.md`
- 出力: `video_manifest.md` の `audio.narration.text` と `audio.narration.tts_text`
- 原則:
  - `script.md` 側では `elevenlabs_prompt` を authoring source、`tts_text` を ElevenLabs v3 に送る final string として扱う
  - `tts_text` は ひらがな寄せを基本にしつつ、`[]` の audio tag を許可する
  - `voice_tags` は bracket なしの生タグで保持し、`tts_text` では順番通りに `[]` を付ける
  - どちらにも `TODO:` 等のメタ情報を書かない（空文字は可。未記入は生成時にエラー）
- 品質基準:
  - narration は cut の物語上の役割に従う
  - opening では、導入として安定した説明を優先し、scene/script に忠実であることを重視する
  - middle では、進展 / トラブル / 揺れを支える
  - ending では、解決 / 帰結 / 余韻を支える
  - 序盤では「無理に抽象的な内面や意味づけを足す」より、物語の入り口として自然であることを優先する
- Claude Code 互換 agent 定義: `.claude/agents/narration-writer.md`

### YouTube Thumbnail Prompt Writer
- 入力: ユーザーが指定した物語名（必須）
- 補助入力: `output/<topic>_<timestamp>/story.md` / `visual_value.md` / `video_manifest.md`（存在すれば参照）
- 出力: ユーザーへ返す `YouTube サムネイル用の構造化プロンプト`
- 目的: 物語名を大きく読ませる装飾文字中心のサムネ用 prompt を作り、背景・構図・可読性・画質条件まで一体で定義する
- 制約:
  - 画像生成 API 自体は呼ばない
  - 文字は既成フォントに寄せず、物語イメージから発想した独創的な造形にする
  - 背景は物語内容に合わせるが、文字可読性を最優先する
  - YouTube thumbnail 向けに `16:9`、`1280x720` 以上、高コントラスト、スマホ視認性を明記する
- Claude Code 互換 agent 定義: `.claude/agents/youtube-thumbnail-prompt-writer.md`

### Reviewer（Director兼務可）
- 入力: scene draft / script
- 出力: `accept | revise` + 理由

### Stage Evaluator
- 入力: `research.md` / `script.md` / `video_manifest.md` / `video.mp4`
- 出力: critic report / aggregator report + `state.txt` の `eval.<stage>.*`
- 役割:
  - authoring-after review slot では最大 5 round の evaluator-improvement loop として動く
  - 各 round では 5 critic agents が generator の出力を rubric/check 単位で独立採点する
  - 1 aggregator agent が critic finding を統合し、`passed|changes_requested` を返す
  - fail reason を次の修正 action に分解する
  - round 5 後も `changes_requested` の場合は human review / explicit override に回す
  - critic / aggregator は canonical artifact、`state.txt`、`p000_index.md` を直接編集しない

### QA / Compliance
- 入力: `research.md`, `story.md`, `script.md`, `video.mp4`
- 出力: QAスコア + pass/fail + 指摘
- 参照: `docs/orchestration-and-ops.md`

### Series Planner（scene-series）
- 入力: `story.md` / `script.md`
- 出力: `series_plan.md`
- Claude Code 互換 agent 定義: `.claude/agents/series-planner.md`

### Scene Evidence Researcher（scene-series）
- 入力: `research.md` + `series_plan.md`（question）
- 出力: `scenes/sceneXX/evidence.md`
- Claude Code 互換 agent 定義: `.claude/agents/scene-evidence-researcher.md`

### Scene Scriptwriter（scene-series）
- 入力: `scenes/sceneXX/evidence.md`
- 出力: `scenes/sceneXX/script.md`（30–60s）
- 品質ゲート: シーン必要性（ストーリー前進 / 矛盾・停滞なし / 登場人物の不可欠性 / テーマ整合）を自己点検して出力末尾に記録
- Claude Code 互換 agent 定義: `.claude/agents/scene-scriptwriter.md`

## プロンプト構成

固定部と動的部に分離する。

- 固定部: 役割の目的 / 出力フォーマット / 品質基準
- 動的部: 入力成果物 / 制約 / 直近の指摘・修正理由

## バージョニング

- 形式: `role@vX.Y.Z`
- 変更履歴は `docs/prompt-changelog.md`（将来作成）に集約する

## Grounding / citation

- Research 出力は source を必須化
- Story/Script は research 参照を明示する
- `visual_value.md` は `research.md` / `story.md` と矛盾しない範囲で設計する

## 参照

- `docs/story-creation.md`
- `docs/script-creation.md`
- `docs/orchestration-and-ops.md`
- `workflow/playbooks/video-generation/kling.md`
