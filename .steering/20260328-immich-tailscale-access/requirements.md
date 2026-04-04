# Requirements

## Context

- ユーザーは Immich を基本的に別 Wi-Fi から使いたい
- 現状の `immich-info.sh` は localhost / LAN URL しか返していない
- Immich は閲覧基盤なので、短命トンネルより安定した閉域アクセスが必要

## Problem

- LAN URL だけでは外出先から使えない
- Tailscale 未導入状態だと、スマホの Codex から「起動して見られる URL を教えて」に十分答えられない

## Goals

- Mac 側で Tailscale を導入しやすくする
- 導入後に Tailscale IP と MagicDNS 名を確認できるスクリプトを追加する
- Immich の接続情報表示に Tailscale URL を含める

## Non-Goals

- ユーザーの Tailscale アカウント作成やスマホアプリのログインを代行すること
- Funnel / Serve の設定
- Tailnet 管理画面の自動操作

## Acceptance Criteria

1. `tailscale-install.sh` `tailscale-info.sh` が追加される
2. `immich-info.sh` が Tailscale 情報を表示できる
3. `immich_remote.md` が別 Wi-Fi 前提の手順に更新される
