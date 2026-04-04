# Requirements

## Goal

`script.md` をナレーション文面 review の正本に寄せ、human review 結果を保持したうえで `video_manifest.md` の `audio.narration.*` へ一方向同期できるようにする。

## Requirements

1. `script.md` は cut ごとに human review 用の明示欄を持つ
2. `script.md` は cut ごとに `tts_text` を持てる
3. `script.md` から `video_manifest.md` へナレーション文面を同期する CLI がある
4. 同期は `approved_narration` / `approved_tts_text` を優先し、未設定時は通常欄へフォールバックする
5. docs / templates / current run artifact が新運用に追従する
6. 最低限の automated test を追加する
