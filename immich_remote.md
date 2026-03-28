# Immich Remote

ToC の `output/` にある画像と動画を、個人用にスマホから見やすくするための運用メモ。

## Goal

- `output/` の成果物を Immich に集約する
- スマホでは Immich アプリだけを見ればよい状態にする
- `CommandMate` は遠隔操作、Immich は成果物閲覧と役割を分ける

## Recommended Shape

- Mac 上で Immich Server を Docker で動かす
- `immich-cli` で ToC の `output/` メディアを同期する
- スマホでは Immich アプリから閲覧する
- 外出先アクセスは将来的に Tailscale を使う
- 常時起動は前提にしない

## Scope

- 対象は `output/` 配下の画像と動画
- markdown / json / txt / logs は同期対象にしない
- まずは手動同期で成立させ、その後に定期同期を足す

## Setup

### 1. Immich Server

セットアップ補助:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/immich-setup.sh
```

```bash
mkdir -p ~/immich
cd ~/immich
curl -L -o docker-compose.yml https://github.com/immich-app/immich/releases/latest/download/docker-compose.yml
curl -L -o .env https://github.com/immich-app/immich/releases/latest/download/example.env
```

`.env` では最低限ここを確認する:

```bash
UPLOAD_LOCATION=./library
```

起動:

```bash
cd ~/immich
docker compose up -d
```

ブラウザ:

```text
http://localhost:2283
```

起動・停止・情報表示:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/immich-start.sh
scripts/ai/immich-info.sh
scripts/ai/immich-stop.sh
```

## 2. Immich CLI

```bash
npm install -g @immich/cli
```

API キー取得後のログイン:

```bash
immich login-key http://localhost:2283 <API_KEY>
```

## 3. ToC Output Sync

追加済みスクリプト:

- `scripts/ai/sync-output-to-immich.sh`

最低限の環境変数:

```bash
export IMMICH_URL=http://localhost:2283
export IMMICH_API_KEY=xxxxxxxx
```

必要なら album 名も付ける:

```bash
export IMMICH_ALBUM=ToC Output
```

手動同期:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/sync-output-to-immich.sh
```

## Sync Policy

同期対象:

- `png`
- `jpg`
- `jpeg`
- `webp`
- `gif`
- `mp4`
- `mov`
- `m4v`
- `webm`
- `mkv`

同期元:

```bash
/Users/kantaro/Downloads/toc/output
```

必要なら run 単位で絞る:

```bash
export IMMICH_SYNC_PATH=/Users/kantaro/Downloads/toc/output/浦島太郎_20260208_1515_immersive
scripts/ai/sync-output-to-immich.sh
```

## Suggested Operation

最初の導入:

1. Immich Server を起動
2. 管理ユーザーを作成
3. API キーを発行
4. `scripts/ai/sync-output-to-immich.sh` を実行
5. スマホで Immich アプリから確認

日常運用:

1. 見たい時だけ `scripts/ai/immich-start.sh`
2. 新しい run の後で手動同期
3. 見終わったら `scripts/ai/immich-stop.sh`

## Smartphone Prompt

スマホの Codex からは、次の短い依頼で十分。

起動して接続先を返す:

```text
Immich を起動して、スマホから見られる URL と同期元 path を教えて
```

初回セットアップだけ進める:

```text
Immich の初回セットアップを進めて、足りない手順だけ教えて
```

同期までやる:

```text
Immich を起動して output を同期し、閲覧 URL を教えて
```

停止する:

```text
Immich を止めて
```

Codex 側で使うスクリプト:

- `scripts/ai/immich-setup.sh`
- `scripts/ai/immich-start.sh`
- `scripts/ai/immich-info.sh`
- `scripts/ai/immich-stop.sh`
- `scripts/ai/sync-output-to-immich.sh`

## Automation Idea

最初は自動起動よりオンデマンド運用を優先する。

理由:

- 閲覧しない時間はコンテナを止めてよい
- 画像・動画ライブラリの整備コストを見てから周期を決めたい

定期同期は、運用が固まってから追加する。

## External Access

外出先から見るなら、Immich は `Pinggy` より `Tailscale` の方が筋がよい。

理由:

- 自前メディア閲覧は VPN 型の方が安全
- 動画閲覧で長時間接続しやすい
- `CommandMate` のように URL が毎回変わる構成にしなくてよい

## Notes

- Immich は閲覧基盤として使う
- ToC の正本は引き続き `output/` 側
- 削除や再整理はまず ToC 側で行い、Immich は派生ビューと考える
