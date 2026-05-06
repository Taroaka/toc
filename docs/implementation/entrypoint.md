# Entrypoint（/toc-run）仕様（正本）

このドキュメントは `.steering/20260117-entrypoint/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

Codex 主軸の assistant command を起点に、Claude Code slash command 互換も保ちながら、最小限の入力で全体フローを起動できるようにする。

## 仕様（想定）

- コマンド: `/toc-run`
- 引数:
  - `topic`（必須）
  - `--dry-run`（任意）
  - `--config`（任意）

## 挙動

- `output/<topic>_<timestamp>/` を作成
- `state.txt` を初期化（1ブロック目を追記）
- `config/system.yaml` を読み込む（`--config` で差し替え可）

## dry-run

- 外部生成（画像/動画/TTS）を実行しない
- research/story/script を生成する

## 参照

- `docs/how-to-run.md`
- `.claude/commands/toc/toc-run.md`（Claude Code 互換 command pack）
- `config/system.yaml`
