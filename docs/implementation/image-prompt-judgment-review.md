# Image Prompt Judgment Review

この文書は、`video_manifest.md` の image prompt を `hard function checks` とは別に、**contextless subagent の judgment review** として確認するための補助フローを定義する。

目的は、`image_generation.review` の機械的な妥当性とは分けて、「この prompt を人間がそのまま生成依頼に渡してよいか」を判断することにある。したがって、このフローでは manifest を修正しない。修正が必要なら、判断結果をもとに manifest 側へ反映する。

## 標準手順

1. `python scripts/build-image-prompt-judgment-review.py --run-dir output/<topic>_<timestamp> [--manifest <path>] [--mode generate_still]` を実行する。
2. helper は run-local の `logs/review/` 配下に次を作る。
   - `logs/review/image_prompt.review_collection.md`
   - `logs/review/image_prompt.review_scope.json`
   - `logs/review/image_prompt.judgment_prompt.md`
   - `logs/review/image_prompt.judgment.md`
3. 生成された `image_prompt.judgment_prompt.md` を、contextless subagent にそのまま渡す。
4. subagent は `image_prompt.review_collection.md` を frozen input として読み、prompt quality を judgment する。
5. subagent の結果は `logs/review/image_prompt.judgment.md` に書き戻す。書き戻せない環境では、同じ内容をそのまま返す。

## 読む対象

subagent は、少なくとも次を読む。

- `docs/system-architecture.md`
- `docs/implementation/image-prompting.md`
- `logs/review/image_prompt.review_scope.json`
- `logs/review/image_prompt.review_collection.md`
- `video_manifest.md`
- `state.txt`

## レポート形式

`logs/review/image_prompt.judgment.md` は、少なくとも次の形を持つ。

```md
# Image Prompt Judgment Review

- status: `passed|failed`
- reviewed_entries: `[...]`
- blocked_entries: `[...]`

## Findings

- `...`

## Notes

- `...`
```

## 補足

- このフローは `scripts/review-image-prompt-story-consistency.py` の hard checks を置き換えない。
- hard checks は manifest の `image_generation.review` を更新する。
- judgment review は、subagent の自然言語判断を run-local artifact に残すための補助層である。
