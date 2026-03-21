# Agent Roles & Prompts（正本）

このドキュメントは `.steering/20260117-agent-roles/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

役割単位で責務を分離し、再現性の高い出力と検証可能性を確保する。

## 実行モデル

- 起点は Claude Code の slash command
- 統括エージェントが `state.txt` を更新
- 役割別の振る舞いは `.claude/agents/*.md` に定義する（例: `director`）

## 役割と責務

### Director（監督）
- 入力: `research.md`
- 出力: `story.md`
- 参照: `docs/story-creation.md`
- エージェント定義: `.claude/agents/director.md`

### Visual Value Ideator
- 入力: `research.md` + `story.md`
- 出力: `visual_value.md`
- 目的: 物語本筋では語り切られないが、動画生成AIで実写風に見せると価値が高い中盤パートを定義する
- 制約:
  - 動画全体の `20% - 80%` に配置する
  - `4-6` カット、各 `4` 秒、ナレーションなしを基本にする
  - 文字ではなく、形 / 光 / 動き / 機構 / ショー性で価値を伝える
- エージェント定義: `.claude/agents/visual-value-ideator.md`

### Scriptwriter
- 入力: `story.md` + `visual_value.md` + scene plan
- 出力: `script.md`
- 参照: `docs/script-creation.md`

### Narration Writer（TTS原稿）
- 入力: `story.md` / `script.md` / `video_manifest.md`
- 出力: `video_manifest.md` の `audio.narration.text`
- 原則: `audio.narration.text` は TTS にそのまま送られるため、`TODO:` 等のメタ情報を書かない（空文字は可。未記入は生成時にエラー）
- 品質基準:
  - 各行で、映像だけでは分かりにくい情報を最低1つ追加する
  - 物理行動の説明より、時間 / 内面 / 因果 / 視点 / 禁忌 / 軽い意味づけを優先する
  - 映像との関係は「説明」より「補完」を優先する
- エージェント定義: `.claude/agents/narration-writer.md`

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
- エージェント定義: `.claude/agents/youtube-thumbnail-prompt-writer.md`

### Reviewer（Director兼務可）
- 入力: scene draft / script
- 出力: `accept | revise` + 理由

### QA / Compliance
- 入力: `research.md`, `story.md`, `script.md`, `video.mp4`
- 出力: QAスコア + pass/fail + 指摘
- 参照: `docs/orchestration-and-ops.md`

### Series Planner（scene-series）
- 入力: `story.md` / `script.md`
- 出力: `series_plan.md`
- エージェント定義: `.claude/agents/series-planner.md`

### Scene Evidence Researcher（scene-series）
- 入力: `research.md` + `series_plan.md`（question）
- 出力: `scenes/sceneXX/evidence.md`
- エージェント定義: `.claude/agents/scene-evidence-researcher.md`

### Scene Scriptwriter（scene-series）
- 入力: `scenes/sceneXX/evidence.md`
- 出力: `scenes/sceneXX/script.md`（30–60s）
- 品質ゲート: シーン必要性（ストーリー前進 / 矛盾・停滞なし / 登場人物の不可欠性 / テーマ整合）を自己点検して出力末尾に記録
- エージェント定義: `.claude/agents/scene-scriptwriter.md`

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
