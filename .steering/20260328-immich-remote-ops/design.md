# Design

## Decision

- Immich の管理操作は `scripts/ai/immich-*.sh` にまとめる
- `~/immich` を既定の Compose ディレクトリとする
- 起動コマンドは `docker compose up -d`、停止は `docker compose down`
- 情報表示は `immich-info.sh` で一本化する

## Why This Shape

- スマホの Codex からは、短い依頼文で既存スクリプトを叩ける形が最も扱いやすい
- 初回セットアップと日常運用を分けることで、失敗時の切り分けが楽になる
- `immich_remote.md` を見れば、スマホから何を言えばよいか分かる状態にしたい

## Changes

### 1. セットアップ補助

- `scripts/ai/immich-setup.sh`
  - `~/immich` 作成
  - `docker-compose.yml` / `.env` をダウンロード
  - `UPLOAD_LOCATION` の既定値をローカル library に揃える

### 2. 起動・停止・情報表示

- `scripts/ai/immich-start.sh`
- `scripts/ai/immich-stop.sh`
- `scripts/ai/immich-info.sh`

### 3. ドキュメント更新

- `immich_remote.md`
  - 常時起動しない前提
  - スマホ向け定型プロンプト
  - 起動後に返る情報

## Verification

- 各スクリプトの実行前提チェックを確認する
- `rg` で `~/immich` `docker compose up -d` `Immich prompt` を確認する
