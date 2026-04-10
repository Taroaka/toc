# Requirements

## Summary

`script.md` と `video_manifest.md` の責務境界を明確化する。

- `script.md` は **物語と映像意図の正本**
- `video_manifest.md` は **画像/動画/音声生成の実装正本**
- `audio.narration.tts_text` は **TTS 専用**であり、image/video generation の主ソースにしない

## Requirements

1. `script.md` は image/video の prompt 本文そのものにはならない
2. `script.md` は scene/cut の映像意図を保持する
3. `script.md` は human review で来た image/video 指示を保持できる
4. `video_manifest.md` は prompt / asset / reference / motion / continuity の実行契約を保持する
5. image generator は `script.md` を意味の参照元、`video_manifest.md` を実装の参照元として併読する
6. video generator も同様に `script.md` を意味の参照元、`video_manifest.md` を実装の参照元として併読する
7. `tts_text` は TTS 以外の generator で主ソースとして扱ってはならない

## Non-goals

- `script.md` に provider 固有 prompt 文法を持ち込まない
- `script.md` を `video_manifest.md` の代替にしない
- image/video generator が `tts_text` だけを見て動く設計にしない
