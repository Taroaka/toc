# Requirements: Codex Built-in Image Provider

## Goal

p500 asset generation と p600 scene image generation では、外部 API image provider ではなく Codex built-in image generation を常用 provider として固定する。

## Success Criteria

- p500 / p600 の image request は `tool: codex_builtin_image` を標準 provider として扱う。
- frontend request、bulk generation、Codex app-server 経由の生成でも同じ provider から逸脱しない。
- `reference_count == 0` は `execution_lane=bootstrap_builtin`、`reference_count > 0` は `execution_lane=standard` を維持する。
- provider 固定の判断は request metadata / 設計書に置き、生成 prompt 本文へ provider 指定を書かない。

## Scope

- canonical docs: `docs/how-to-run.md`, `docs/implementation/image-prompting.md`, `docs/implementation/asset-bibles.md`, `docs/system-architecture.md`, `docs/video-generation.md`
- frontend design docs: `server/web/docs/brand-design/interaction-principles.md`
- templates: `workflow/video-manifest-template.md`, `workflow/scene-video-manifest-template.md`

## Out of Scope

- 動画 provider / TTS provider の変更
- 生成 prompt 本文への provider 文言追加
