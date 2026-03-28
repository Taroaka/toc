# Design

## Prompt Collection State

review の正本は `image_prompt_collection.md` に持つ。各 cut は次を持つ。

- `agent_review_ok`
- `human_review_ok`
- `agent_review_reason_keys`
- `agent_review_reason_summary`

subagent は review 実行後に `agent_review_ok` と reason keys を更新する。`agent_review_reason_codes` は互換 alias として読み書きできるが、正本の名前は `agent_review_reason_keys` とする。fix 後に再 review して finding が消えれば、`agent_review_ok=true` かつ reason keys を空に戻す。

## Review

- source text は narration + story scene text + script scene text
- 検査対象:
  - prompt が必須 6 ブロック `[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`, `[連続性]`, `[禁止]` をすべて持つか
  - prompt が self-contained で、`sceneXX_cutYY` や `前カット` / `次カット` / `前のprompt` のような参照依存表現を含まないか
  - prompt が日本語で完結しており、`rideable` のような英語 shorthand を含まないか
  - missing `character_ids`
  - missing `object_ids`
  - prompt が expected character/object を明示していない
  - prompt が environment-only に流れている
  - story 上の relation/blocking が prompt から落ちている
- 必須ブロック欠落の finding code は `missing_required_prompt_block`
- 独立性違反の finding code は `prompt_not_self_contained`
- 英語 shorthand の finding code は `non_japanese_prompt_term`
- autofix は `character_ids` / `object_ids` の追加のみ

## Runtime Gate

- `generate-assets-from-manifest.py` は画像生成前に
  - prompt collection export
  - review 実行
  - missing `character_ids` autofix
  - prompt collection を更新
  - `agent_review_ok=false` かつ `human_review_ok=false` の cut が残れば fail
- 人間は許容する cut のみ `--set-human-review sceneXX_cutYY` で `human_review_ok=true` を付ける
