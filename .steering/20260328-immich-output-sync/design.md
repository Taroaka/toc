# Design

## Decision

- Immich の運用メモは root 直下の `immich_remote.md` に置く
- 実装は「Immich サーバ導入補助」と「ToC の output 同期スクリプト」に分ける
- 同期対象はまず `output/` 配下の画像・動画だけに絞る

## Why This Shape

- 目的は閲覧基盤であり、ToC 本体の生成フローとは分離した方が分かりやすい
- `output/` には markdown/json/log も多く含まれるため、Immich に送る対象をメディアだけに限定した方が実運用でノイズが少ない
- `immich-cli` は導入後の再利用性が高く、手動同期と cron/automation の両方へ拡張しやすい

## Changes

### 1. Immich 導入ガイド追加

- `immich_remote.md` を追加
- 内容:
  - 目的
  - 構成
  - Docker Compose セットアップ
  - `immich-cli` 導入
  - API キー取得
  - 手動同期
  - 将来の自動化
  - Tailscale 補足

### 2. Output 同期スクリプト追加

- `scripts/ai/sync-output-to-immich.sh` を追加
- 役割:
  - `IMMICH_URL`
  - `IMMICH_API_KEY`
  - `IMMICH_ALBUM`
  - `IMMICH_SYNC_PATH`
  を受けて `output/` のメディアをアップロード

### 3. 対象メディアの抽出方針

- 画像: `png jpg jpeg webp gif`
- 動画: `mp4 mov m4v webm mkv`
- まずは `output/` 全体からメディアファイルのみを抽出して送る

## Verification

- スクリプトの `--help` 相当を確認する
- `rg` で `IMMICH_URL` `IMMICH_API_KEY` `output/` が入っていることを確認する
