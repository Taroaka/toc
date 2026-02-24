# Kling 3.0 / Kling 3.0 Omni（ドキュメント置き場）

このフォルダは、ToC リポジトリの **Kling 連携（`toc/providers/kling.py` / `scripts/generate-assets-from-manifest.py`）** に関連する情報を、参照しやすい形で集約するためのメモ置き場です。

## 前提（重要）

- `klingai.com` 側の公式ドキュメントは、クローラ遮断などで自動取得できないことがあります。
- そのため現時点では、**第三者のゲートウェイ/ラッパーの公開ドキュメント**も含めて参照し、差分に備えて「差し替え可能」な設計（env / extra JSON）を優先します。

## このrepoでの使い方（最短）

- 既定の動画プロバイダ: `kling_3_0`
- Omni を使う: `video_generation.tool: "kling_3_0_omni"`（manifest）
- Omni のモデル名: `KLING_OMNI_VIDEO_MODEL`（必要なら差し替え）
- 任意パラメータの透過: `KLING_EXTRA_JSON` / `KLING_OMNI_EXTRA_JSON` または CLI の `--kling-*-extra-json`
- 認証（公式推奨）: `KLING_ACCESS_KEY` / `KLING_SECRET_KEY`（JWT を自動生成して `Authorization: Bearer <token>` で送信）

詳細は `integration-in-this-repo.md` を参照。

## 参照リンク（更新の起点）

- 公式 Developer Docs（要ログイン/閲覧制限の可能性あり）: https://app.klingai.com/global/dev/document-api/apiReference/user/whatIsKling
- 公式 API base URL（このrepo既定）: `https://api.klingai.com`（リージョン別ドメインが案内される場合は `KLING_API_BASE` を上書き）
- Kling API Docs（第三者: `klingapi.com`）: https://klingapi.com/docs
- Kling 3.0 Omni（第三者: PiAPI）: https://piapi.ai/docs/kling-api/kling-3-omni-api
- Kling 3.0 Pricing（第三者: kling3-ai.com）: https://www.kling3-ai.com/pricing
- EvoLink Kling API（第三者ゲートウェイ）: https://docs.evolink.ai/en/api-manual/video-series/kling

## EvoLink を使う場合（このrepo）

`EVOLINK_API_KEY` を設定すると、`kling_3_0` / `kling_3_0_omni` は EvoLink 経由を優先します。  
メモ: `evolink.md`
