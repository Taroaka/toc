# Requirements

## Context

- `state.txt` は canonical state だが、現状は `status=RESEARCH|STORY|SCRIPT|VIDEO|QA|DONE` のような粗い段階しか標準化されていない
- 実運用では「調査完了」「ナレーション完了」「render 完了」など、1物語の制作状況を `state.txt` だけで把握したい
- append-only を維持したまま、工程ごとの進行状態を表現したい

## Problem

- `state.txt` を見ても、Video ステージ内部のどこまで終わったかが分からない
- `run_status.json` は derived view だが、正本である `state.txt` 側に必要な粒度が無い
- 各作業の開始時/完了時に何を書き込むかの運用が正本に明記されていない

## Goals

- `state.txt` に工程別状態を表す標準キーを追加する
- 1物語フォルダの `state.txt` を見れば、主要工程の完了状況を読めるようにする
- 各作業でいつ何を append するかを docs に明記する

## Non-Goals

- 既存スクリプト全体の実装変更
- DB や別状態ストアの導入

## Acceptance Criteria

1. `workflow/state-schema.txt` に stage 単位の標準キーが定義される
2. `docs/data-contracts.md` に `status` と `stage.*.status` の役割分担が明記される
3. `docs/how-to-run.md` か `docs/orchestration-and-ops.md` に、各作業開始/完了時の追記フローが記載される
