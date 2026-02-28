# Cut planning from narration (requirements)

## Background

これまでの `video_manifest.md` 運用では、画像/動画生成の設計が先に固まりやすく、ナレーション（ElevenLabs）による実秒数とカット数/尺の整合が後追いになりがちだった。

## Goals

- **1カット = 1ナレーション** を基本単位にする
- **メインカット（最低1つ）: 5–15 秒**（ナレーション実秒ベース）
- **サブカット（任意 / 複数可）: 3–15 秒**
  - 15秒を超えそうなら、似た役割のカットを 2 本以上に分割する
  - 15秒以下でも「scene と narration の両方が揃った時点」で、必要なら 2 本以上に分割する（都度判断）
- この考え方を `/toc-run` / `/toc-scene-series` / `/toc-immersive-ride` に適用する
  - ただし **`/toc-immersive-ride --experience cloud_island_walk`（哲学を島でPOV視点で語る体験）は変更しない**

## Non-goals

- 既存の `output/` 生成物の修正
- TTS の品質/声色/台詞調整の自動最適化
