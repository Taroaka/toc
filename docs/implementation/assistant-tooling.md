# Assistant tooling（Claude Code / Codex）仕様（正本）

このドキュメントは `.steering/20260131-improve-claude-code/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

ToCリポジトリに同梱されている `improve_claude_code/` を「置いてあるだけ」にせず、

- Claude Code で command pack / agents / skills を使える
- tmux multi-agent を Claude / Codex の両方で起動できる
- Codex 側でも運用（plan/tdd/verify 等）を再現できる

状態にする。

## 何がどこにあるか

### 同梱元（vendor）

- `improve_claude_code/`
  - `.claude/commands/`（汎用 slash command pack）
  - `agents/`（planner, code-reviewer 等）
  - `skills/`（tdd-workflow, verification-loop 等）
  - `shutsujin_departure.sh`（tmux multi-agent 起動）

### ToC側（実際に使う場所）

- Claude Code:
  - `.claude/commands/improve/`（上記 command pack を同期）
  - `.claude/agents/`（agents を同期）
  - `.claude/skills/`（vendor skills 本体 + ToC shared skills の symlink）
- Codex:
  - `skills/`（ToC 独自 shared skills の正本）
  - `codex_skills/`（互換 alias。`skills/` を指す）
  - `scripts/ai/install-codex-skills.sh`（`skills/` から `~/.codex/skills` へインストール）

## Claude Code: コマンド/エージェント/スキル

- 追加されたコマンドは `.claude/commands/improve/` 配下（例: `/plan`, `/tdd`, `/verify`, `/code-review`）
- 追加されたエージェントは `.claude/agents/` 配下（例: `planner.md`, `code-reviewer.md`）
- 追加されたスキルは `.claude/skills/` 配下
- vendor 由来の汎用スキル（例: `tdd-workflow/`, `verification-loop/`）は `.claude/skills/` に実体を持つ
- ToC 独自スキル（例: `folktale-researcher/`, `neta-collector/`）は `.claude/skills/<name> -> ../../skills/<name>` の symlink で shared 正本を参照する

## tmux multi-agent（Claude / Codex）

このリポジトリでは `scripts/ai/multiagent.sh` を起点にする。

```bash
# Claude Code で起動
scripts/ai/multiagent.sh --engine claude

# Codex CLI で起動
scripts/ai/multiagent.sh --engine codex
```

前提:
- `tmux` が必要（macOS 例: `brew install tmux`）

## ToCの並列開発（推奨パターン）

「research → story/script → scene雛形 → scene別制作」は依存が強いので、共有ファイルを複数足軽が同時編集しない。

- Phase 1（並列）: 各足軽は `scratch/ashigaruN/research_notes.md` に調査結果を書き、**1人が research.md に統合**
- Phase 2（並列）: 各足軽は `scratch/ashigaruN/story_notes.md` に案を書き、**1人が story.md（or script.md）に統合**
- Phase 3（直列）: **1人**が `scripts/toc-scene-series.py` で `scenes/` を雛形生成
- Phase 4（並列）: sceneごとに `scenes/sceneXX/` 配下だけ編集して完成（競合なし）
- Phase 5（直列）: **1人**が全体サマリ作成

準備スクリプト（scratch/run-dir作成）:

```bash
python scripts/ai/toc-scene-series-multiagent.py "topic"
```

## Codex: skills

ToC 独自スキルの正本は `skills/` に置き、Claude Code / Codex の両方が同じ `SKILL.md` を参照する。
`codex_skills/` は既存参照を壊さないための互換 alias として残す。

Codex へは下記で `skills/` から `~/.codex/skills/` へ同期する。

- インストール:

```bash
scripts/ai/install-codex-skills.sh
```

主なスキル:

- `improve-workflow`: plan→implement→verify の堅い開発ループ
- `folktale-researcher`: 国/地域別の民話・神話ネタ出し→ToC調査テンプレへの落とし込み
- `neta-collector`: ネタ収集の入口（各国物語/自己啓発人物/AI発案/時代解説の振り分け）
- `selfhelp-trend-researcher`: 話題の自己啓発系人物の候補出し→紹介骨格（Hybridで未検証も明示）
- `ai-idea-studio`: AI発案のオリジナル案を量産→1案深掘り（制作可能な骨格）
- `era-explainer`: 時代解説（例: 縄文）を cloud_island_walk 等の体験フォーマットへ落とし込み
- `vertical-shorts-creator`: 承認済みの横動画から縦ショート（9:16, ~60秒）を作る（scene選定→コマンド提示）

補助資料や共通ナレッジを shared skills 間で使い回す場合は `skills/_shared/` に置き、installer の対象外にする。

## Session bootstrap / verify

日常運用の最小ルーチン:

```bash
scripts/ai/session-bootstrap.sh
```

固定手順:

1. `cwd` 確認
2. `git status` / `git log`
3. 直近 run の確認
4. pending gate の確認
5. fast verify

共通 verify 入口:

```bash
python scripts/verify-pipeline.py \
  --run-dir output/<topic>_<timestamp> \
  --flow toc-run|scene-series|immersive \
  --profile fast|standard
```

root guide から外した検索/探索ルールは、引き続き `rg` / `fd` を正とする。

## Claude Code: rules（任意・グローバル）

`improve_claude_code/rules/*.md` を `~/.claude/rules/` にコピーしてグローバルに適用する。

```bash
scripts/ai/install-claude-rules.sh
```

※ 影響範囲は全プロジェクトになるため、不要なら削除/運用で調整する。
