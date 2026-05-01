# Open Decisions

本書は、未確定事項（TBD）を集約する。

## Providers
- image: Google Nano Banana 2（`google_nanobanana_2`）
- image (alt): Gemini 3.1 Flash Image（`gemini_3_1_flash_image` / `gemini-3.1-flash-image-preview`）
- video: Kling 3.0（default。`video_generation.tool: kling_3_0`）
- video (omni): Kling 3.0 Omni（`video_generation.tool: kling_3_0_omni`）
- video (alt): Seedance（BytePlus ModelArk。`video_generation.tool: seedance`）
- note: Google Veo は安全のためこのリポジトリでは無効化している
- TTS: ElevenLabs（voice/model/output_format は運用で確定）
- LLM provider is LangChain (API-based)
- 候補整理/調査リスト: `docs/video-production-research.md`

## Claude Code entrypoint
- `/toc-run` の実装方法（Claude Code側の具体設定）

## Rendering details
- 字幕（SRT）の生成方法
- BGM/SFX の扱い（内製/生成、音量基準）

## Data/Logging
- `orchestration_manifest.md` の正本（ファイル/DBの役割分担）
- `run_status.json` を DB 的にどこまで使うか

## ADR backlog

- Accepted decisions are moved to `docs/adr/`
