---
name: hero-journey-cinematic-setpieces
description: 物語の重要な道具・舞台装置を、映像上の役割と一貫した外観を持つ ToC asset bible に設計する。
metadata:
  tags: story, hero-journey, cinematic, setpiece, props, immersive
---

# Cinematic Setpieces

重要な道具や舞台装置の映像設計を求められたときに使う。既存の物語構造と原作の意味を保ち、別の物語のアイテムや一律の英雄の旅フェーズを押し込まない。

- 設計と schema は `docs/implementation/asset-bibles.md`、具体的な手順は `workflow/playbooks/script/hero-journey-cinematic-setpieces.md` を必要な範囲で読む。
- プロンプトを執筆する場合は `docs/implementation/image-prompting.md` の現行形式を使う。
- `video_manifest.md` の `assets.object_bible` に映画での役割、映像から伝わる情報、視覚的特徴、材質・構造・機構・不変条件を記録する。
- story scene の `image_generation.object_ids` と asset 定義を対応づける。reference scene / `reference_images` の要件は選択した生成 lane の現行契約に従う。
- 設計完了は必要な定義・参照・schema の整合で確認する。画像生成まで依頼された場合だけ、既存の asset materialization / generation 手順へ進む。
