# Requirements

## Context

- ユーザーは Immich を `output/` の個人閲覧基盤として使いたい
- スマホ上の Codex から「起動して」「見れるパスを教えて」という運用をしたい
- 現時点では `~/immich` も未作成で、Docker Compose も未配置

## Problem

- Immich を使うまでの操作が手順書ベースだと、スマホから都度指示するには長い
- 起動、停止、URL 確認、初回セットアップがバラバラだと再利用しにくい

## Goals

- Immich の初回セットアップ補助、起動、停止、状態確認をスクリプト化する
- スマホ上の Codex から短いプロンプトで実行できるよう、定型プロンプトを文書化する
- 起動後にローカル URL、LAN URL、同期元 path をまとめて返せるようにする

## Non-Goals

- Immich アカウント作成や API キー発行を自動化すること
- Tailscale 自体のセットアップ
- Immich の cron 常駐運用の導入

## Acceptance Criteria

1. `scripts/ai/immich-setup.sh` `immich-start.sh` `immich-stop.sh` `immich-info.sh` が追加される
2. `immich_remote.md` に、スマホから使う定型プロンプトが追記される
3. `immich-start.sh` 実行後に接続先と同期元 path を確認できる
