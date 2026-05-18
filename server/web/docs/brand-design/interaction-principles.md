# Interaction Principles

## Core Workflow

`/image_gen` の主要 workflow は次の順に固定する。

1. run folder を選ぶ
2. asset / scene を切り替える
3. 同時生成枚数を決める
4. prompt と reference image を確認・調整する
5. 単体または一括で candidate を生成する
6. candidate を選ぶ
7. zip download または repo insertion で外へ出す

UI はこの workflow の邪魔になる説明や装飾を置かない。

## Prompt Editing

prompt text field は request md から初期化する。ユーザーが画面上で編集した prompt は、その生成リクエストに使う。

v1 では画面上の prompt 編集を md へ自動反映しない。md 更新は right chat pane からユーザーが Codex に依頼する導線にする。

## Reference Selection

reference image は `<run_dir>/assets/**/*.{png,jpg,jpeg,webp}` から作る。

multi-select の期待:

- 何枚でも選べる
- thumbnail を出す
- label は拡張子なし filename
- selected state が分かる

p500 / p600 の image item は、frontend からの単体生成・一括生成・Codex app-server 経由の生成のいずれでも `codex_builtin_image` 固定で扱う。外部 API provider へ切り替えない。`reference_count == 0` の item だけ no-reference work として `execution_lane=bootstrap_builtin` に残し、参照あり item は `execution_lane=standard` のまま Codex built-in image generation に渡す。

## Generation

単体生成:

- card 内 button から、その item だけ生成する
- prompt と選択 reference images を使う
- generated candidate は `assets/test/image_gen_candidates/<item_id>/candidate_XX.*` に保存する

一括生成:

- visible grid の item を対象にする
- nested item の `run_id` / `kind` は信用せず、画面上の parent selection を正とする
- bulk footer から実行する
- concurrency は UI 上の candidate count と server limit の範囲内で扱う

## Repo Insertion

一括 repo 内挿入は、選択 candidate を md の `output` path へコピーする。

ルール:

- source は candidate directory 配下だけ許可
- destination は run dir 内の `assets/` 配下だけ許可
- 既存 canonical file は `assets/test/image_gen_backups/<timestamp>/` に退避してから上書きする
- `state.txt` は置き換えない。必要な履歴がある場合は append-only

## Right Chat Pane

right chat pane はユーザーとの通常 chat 専用であり、画像生成 job log を表示しない。

役割:

- prompt 設計の相談
- md file の編集依頼
- reference の見直し
- command / file edit approval の確認 UI

画像生成の進捗、candidate status、failure は left workspace の該当 card に出す。

## Error Handling

ユーザーに出す error は短く、次の行動が分かるものにする。

- run folder not found
- request file not found
- reference image not found
- Codex app-server disabled
- imageGeneration.savedPath missing

server 内部 path や stack trace は UI に出さない。
