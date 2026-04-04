# Requirements

## Goal

土日だけ Mac をサーバ用途で起動し続けやすくする。

## Why

- CommandMate / Immich / Tailscale を週末だけ常時使いたい
- `pmset` の恒久変更は戻し忘れや影響範囲が広い
- ノート Mac では週末運用だけを軽く切り替えたい

## Requirements

- `sudo` なしで使える
- 週末運用の開始 / 停止を明確に切り替えられる
- 既に起動中かどうか確認できる
- Remote Work / Immich の運用メモに反映する

## Non-Goals

- launchd やカレンダーベースの完全自動化
- macOS の system-wide sleep 設定の恒久変更
