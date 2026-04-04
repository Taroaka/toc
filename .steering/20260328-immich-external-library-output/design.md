# Design

## Decision

`output/` を managed upload で複製する構成は残しつつ、閲覧用途では Immich External Library を使えるようにする。

## Approach

1. `~/immich/docker-compose.yml` の `immich-server` に ToC `output/` の bind mount を追加する
2. 将来の再セットアップでも mount が入るよう `scripts/ai/immich-setup.sh` を更新する
3. 既存環境に対して mount を反映し再起動できる補助スクリプトを追加する
4. `scripts/ai/immich-info.sh` に host path / container path を出す
5. `immich_remote.md` に External Library 作成手順を追記する

## Mounts

- Host path: `/Users/kantaro/Downloads/toc/output`
- Container path: `/external/toc-output`
- Mode: `read-only`

## Tradeoffs

- 長所: 元の run フォルダ名が残る。再同期不要。スマホの Folder View と相性が良い
- 短所: UI 上で一度 External Library を作る必要がある。既存の managed upload asset は残る
