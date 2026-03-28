# Design

## Decision

- `remote_work.md` は記事の要約ではなく、ToC 用の実行チェックリストとして書く
- 構成は「目的」「前提」「フェーズ別 TODO」「初回運用手順」「注意点」に分ける
- 実務でそのまま使えるよう、各フェーズに確認条件と具体コマンドを置く

## Why This Shape

- 記事由来の知識をそのまま転記すると、ToC で次に何をするかが曖昧なままになる
- チェックリスト形式なら、PC 側準備とスマホ側確認を段階的に消化できる
- root 直下に置くことで、記事メモではなく運用 TODO としてすぐ開ける

## Changes

### 1. root 直下の運用 TODO を追加

- `remote_work.md` を追加し、以下を含める
  - ゴール
  - 必要ツール
  - セットアップ TODO
  - LAN 利用と外部公開の分岐
  - ToC での初回起動ルーチン
  - スマホからやる操作
  - セキュリティ注意点

### 2. ToC 固有の実務メモを埋め込む

- `scripts/ai/session-bootstrap.sh`
- git worktree
- Markdown 編集対象として `remote_work.md` 自身や `movie_todo.md` を例示

## Verification

- Markdown として読めることを目視確認する
- `rg "CommandMate|session-bootstrap|worktree" remote_work.md` で主要論点が入っていることを確認する
