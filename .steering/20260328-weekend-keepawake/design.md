# Design

## Decision

`pmset` ではなく `caffeinate` を使う。

## Rationale

- `caffeinate -dimsu` はユーザー権限で動く
- 停止すると元の省電力挙動に戻る
- 週末だけのサーバ運用に向く

## Implementation

- `scripts/ai/weekend-keepawake-start.sh`
  - 既存プロセス確認
  - PID file 作成
  - `caffeinate -dimsu` をバックグラウンド起動
- `scripts/ai/weekend-keepawake-stop.sh`
  - PID file から停止
  - 残骸 PID file を掃除
- `scripts/ai/weekend-keepawake-status.sh`
  - 起動状態と PID を返す

## State

- PID file: `~/.toc-runtime/weekend-keepawake.pid`

## Tradeoffs

- ログインユーザーのセッションに依存する
- 再起動後は再度 start が必要
