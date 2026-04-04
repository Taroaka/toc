# Immich Remote

ToC の `output/` にある画像と動画を、個人用にスマホから見やすくするための運用メモ。

## Current Status

- Immich Server は Mac 上で起動確認済み
- `http://127.0.0.1:2283` でローカル接続できる
- `http://192.168.11.14:2283` で LAN 接続できる
- Tailscale は導入済み
- `http://100.100.122.55:2283` で Tailscale IP 接続できる
- `http://m2-air.taile21295.ts.net:2283` で Tailscale DNS 接続できる
- スマホアプリからも Immich 接続確認済み
- `immich-cli` による `output/` 同期は成功済み
- 次の改善対象は `output/` を External Library として見せて、run 名を保ったフォルダ閲覧を成立させること

## Goal

- `output/` の成果物を Immich に集約する
- スマホでは Immich アプリだけを見ればよい状態にする
- `CommandMate` は遠隔操作、Immich は成果物閲覧と役割を分ける

## Recommended Shape

- Mac 上で Immich Server を Docker で動かす
- 閲覧の正本は `output/` を External Library として mount する
- 必要な場合だけ `immich-cli` で managed upload にも同期する
- スマホでは Immich アプリから閲覧する
- 外出先アクセスは Tailscale を使う
- 常時起動は前提にしない

## Scope

- 対象は `output/` 配下の画像と動画
- markdown / json / txt / logs は External Library に見えても Immich asset にはならない
- run 単位フォルダ名をスマホでたどれることを優先する

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

External Library mount を既存環境に反映:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/immich-enable-output-external-library.sh
```

### 1.5 Tailscale

Mac 側:

```bash
cd /Users/kantaro/Downloads/toc
scripts/ai/tailscale-install.sh
scripts/ai/tailscale-info.sh
```

iPhone 側:

1. Tailscale アプリを入れる
2. Mac と同じアカウントでログインする
3. Tailscale を有効化する

## 2. Immich CLI

```bash
npm install -g @immich/cli
```

API キー取得後のログイン:

```bash
immich login-key http://localhost:2283 <API_KEY>
```

## 3. External Library First

Immich の managed upload は `/data/upload/<uuid>/...` 配下に保存されるため、ToC の `output/<topic>_<timestamp>` 構造は残らない。

run 名を保ってたどりたい場合は、`output/` を External Library として参照する。

Host path:

```bash
/Users/kantaro/Downloads/toc/output
```

Container path:

```bash
/external/toc-output
```

Immich UI:

1. `Administration`
2. `External Libraries`
3. `Create Library`
4. Folder path に `/external/toc-output`
5. `Scan New Library Files`
6. 必要なら `Folder View` を有効化して run フォルダ単位で見る

## 4. Optional Managed Upload Sync

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

## Managed Upload Sync Policy

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
2. `scripts/ai/immich-enable-output-external-library.sh` を一度だけ実行
3. Immich UI で External Library を作成
4. `Scan New Library Files`
5. Tailscale を両端末で有効化
6. スマホで Immich アプリから Folder View を確認
7. 必要な場合だけ `scripts/ai/sync-output-to-immich.sh` を実行

日常運用:

1. 見たい時だけ `scripts/ai/immich-start.sh`
2. 新しい run の後で手動同期
3. 見終わったら `scripts/ai/immich-stop.sh`

週末だけ外出先から見られる状態を保つ:

1. 金曜夜か土曜朝に `scripts/ai/weekend-keepawake-start.sh`
2. `scripts/ai/immich-start.sh`
3. Tailscale を有効なままにする
4. 日曜夜に `scripts/ai/immich-stop.sh`
5. `scripts/ai/weekend-keepawake-stop.sh`

今の最短次手:

1. `scripts/ai/immich-enable-output-external-library.sh` を実行する
2. Immich UI で `/external/toc-output` を External Library として追加する
3. `Scan New Library Files` を実行する

## Smartphone Prompt

スマホの Codex からは、次の短い依頼で十分。

起動して接続先を返す:

```text
Immich を起動して、Tailscale でスマホから見られる URL と同期元 path を教えて
```

初回セットアップだけ進める:

```text
Immich の初回セットアップを進めて、足りない手順だけ教えて
```

同期までやる:

```text
Immich を起動して output を同期し、Tailscale で見られる URL を教えて
```

External Library の path を返す:

```text
Immich を起動して、Tailscale URL と external library の container path を教えて
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
- `scripts/ai/immich-enable-output-external-library.sh`
- `scripts/ai/sync-output-to-immich.sh`

## Automation Idea

最初は自動起動よりオンデマンド運用を優先する。

理由:

- 閲覧しない時間はコンテナを止めてよい
- 画像・動画ライブラリの整備コストを見てから周期を決めたい

定期同期は、運用が固まってから追加する。

## External Access

外出先アクセスの優先順位:

1. `http://<tailscale-ip>:2283`
2. `http://<magic-dns-name>:2283`
3. LAN 内だけなら `http://192.168.11.14:2283`

現在の接続先:

1. `http://100.100.122.55:2283`
2. `http://m2-air.taile21295.ts.net:2283`
3. LAN 内だけなら `http://192.168.11.14:2283`

理由:

- 自前メディア閲覧は VPN 型の方が安全
- 動画閲覧で長時間接続しやすい
- URL を固定に近い感覚で扱える
- `CommandMate` の `Pinggy` と役割分担しやすい

## Notes

- Immich は閲覧基盤として使う
- ToC の正本は引き続き `output/` 側
- 削除や再整理はまず ToC 側で行い、Immich は派生ビューと考える
