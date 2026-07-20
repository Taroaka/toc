# Requirements

## Goal

画像 prompt review を「任意の入力文を自由解釈するレビュー」ではなく、物語・scene・cut・asset の正本キーを、登録済みの描画 group と review 観点へ投影する拡張可能な契約へ変更する。

## Success criteria

- prompt へ影響する正本キーは `required|conditional|none` の relevance を持つ registry entry で宣言される。
- 各 registry entry は source key、target group、変換責務、deterministic check、semantic review 観点を持つ。
- compiler が採用できる全 `drawable_prompt_ir` group は registry に一意に登録され、group 追加時に registry 未登録ならテストが失敗する。
- deterministic reviewer は registry から group の必要性を解決し、dependency、`required_groups`、fragment、provider prompt の trace を検査する。
- `story_time` と `time_of_day` は正本値との exact binding に加え、同値を持つ fragment と provider prompt まで検査する。
- semantic image prompt review pack は、その cut で active な registry rule と、agent が判断すべき `include|omit|add|replace` の観点を含む。
- prompt へ投影しないキーも `relevance: none` と理由を明示でき、未登録キーを provider prompt へ自動転記しない。

## Scope

- image prompt projection registry
- image prompt compiler の group order
- deterministic image prompt review
- semantic image prompt review collection
- 関連する tests / canonical docs

## Out of scope

- 全story/script/manifestキーの一括登録
- 過去runの自動migration
- 任意のユーザー原文を直接provider promptへ流すこと
- 生成済み画像そのものの視覚評価
