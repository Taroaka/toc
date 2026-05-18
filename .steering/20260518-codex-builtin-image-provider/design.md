# Design: Codex Built-in Image Provider

## Decision

p500 / p600 の画像 provider は `codex_builtin_image` に固定する。これは Codex built-in image generation（現行想定 `gpt-image-2`）を Codex app-server 経由で使う運用を指す。

## Lane Rule

- `reference_count == 0`: `execution_lane=bootstrap_builtin`
- `reference_count > 0`: `execution_lane=standard`

lane は参照有無の実行分類であり、provider 選択ではない。参照ありでも provider は `codex_builtin_image` のままにする。

## Frontend / App-server Boundary

frontend は image request の prompt と references を編集・送信する UI であり、provider selector にはしない。Codex app-server は transport / execution boundary であり、image provider 名は `codex_builtin_image` として記録する。

## Prompt Boundary

provider 固定は設計・metadata の責務である。生成 prompt 本文には `codex_builtin_image`、Codex app-server、外部 API 禁止などの運用メタを書かない。
