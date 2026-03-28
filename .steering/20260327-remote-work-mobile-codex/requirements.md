# Requirements

## Context

- ユーザーは Qiita 記事「Codex CLI をスマホから操作する方法」を読んだ上で、ToC リポジトリ向けに実行 TODO を整理したい
- ToC では日常運用の正本が `docs/`, `workflow/`, `scripts/` にありつつ、実務上の短期実行計画は root 直下の補助ドキュメントで管理されることがある
- スマホからの Codex 操作は、ToC 本体の生成フロー変更ではなく、開発運用レイヤーの整備にあたる

## Problem

- 記事の内容は一般的なセットアップ手順であり、ToC リポジトリで何を準備し、どこまで実施済みかが分からない
- スマホ運用にはインストール、認証、公開方式、ワークディレクトリ登録、運用ルールの複数論点があり、順番が曖昧だと途中で止まりやすい

## Goals

- ToC 向けに、スマホから Codex を操作するための TODO を root 直下の `remote_work.md` にまとめる
- その TODO が「まず何をやるか」「次に何を確認するか」「どこまで整えば運用開始か」を追える構成にする
- ToC 特有の運用前提として、`scripts/ai/session-bootstrap.sh` や git worktree を踏まえた実務メモを含める

## Non-Goals

- CommandMate 自体のコード実装やリポジトリへの組み込み
- ネットワーク公開の自動化スクリプト追加
- README や `docs/how-to-run.md` の大規模改訂

## Acceptance Criteria

1. root 直下に `remote_work.md` が追加される
2. `remote_work.md` に、スマホ運用の TODO が段階別チェックリストとして整理されている
3. `remote_work.md` に、ToC リポジトリで使う具体コマンドや運用上の注意点が含まれている
