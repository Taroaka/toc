# Requirements

## Goal

Immich 上で ToC の `output/` を、ランダムな managed storage 配下ではなく、元のフォルダ構造に近い形で閲覧できるようにする。

## Why

- `immich upload` で取り込んだ managed asset は `/data/upload/<uuid>/...` 配下に保存され、ToC の run 単位フォルダ名が見えにくい
- スマホから `output/` を run 単位でたどりたい
- 個人閲覧用途では、コピーして再配置するより `output/` をそのまま External Library として参照する方が目的に合う

## Requirements

- Immich server コンテナから ToC の `output/` を read-only で参照できる
- 既存の起動手順に大きな破壊を入れない
- 運用メモに「managed upload と external library の違い」を明記する
- スマホ確認に必要な container path を Codex から返せる

## Non-Goals

- 既存 managed upload asset の自動移行
- Immich API を使った external library の自動作成
- metadata sidecar や削除権限の付与
