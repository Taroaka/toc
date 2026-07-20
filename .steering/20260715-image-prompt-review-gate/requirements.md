# Requirements

## Goal

任意の動画依頼から作られた抽象的な物語・cutキーを、そのまま画像 prompt へ転記せず、画像生成前の agent review で採用・除外・補完してから provider request を確定する。

## Success criteria

- 初期 compile で作る `api_prompt_payload.prompt` / request snapshot は review 前の draft として扱う。
- p630/p640 の critic report を固定文で `passed` にしない。
- image prompt reviewer は、各cutで抽象キーを `include / omit / add / replace` の観点から判断する。
- reviewer は時代背景、人物・小道具・場所・参照画像、reveal順、正負矛盾、制作メタ混入、同一scene内の重複を確認する。
- producer repair は正本の `first_frame_visual_plan` と依存IDを修正し、provider prompt を直接手編集しない。
- repair 後は `video_manifest.md` の v2 payload、`image_generation_requests.md`、`image_generation_request_snapshot.json` を同じ revision へ再生成する。
- semantic image prompt review が通るまで p650 request freeze を完了扱いにしない。
- `must_not_advance_beyond` の肯定的な次cut設計文を `not_yet_happened_in_still` へ自動転記しない。

## Scope

- frontend create runner の p600 review / freeze 状態
- image prompt semantic review pack と producer repair contract
- image_api_prompt_v2 の再コンパイルと request snapshot 同期
- Cinderella を含む scaffold の temporal constraint projection
- 関連テストと設計文書

## Out of scope

- reviewer 自体を deterministic rule のみへ置き換えること
- 生成済み画像の視覚品質レビュー
- 過去 run の自動 migration

