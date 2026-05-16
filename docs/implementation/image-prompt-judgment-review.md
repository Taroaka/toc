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

## 追加レビュー観点

- prompt 本文が画像生成 API に渡す文として成立しているかを見る。
- `物語「<topic>」の scene10`、`scene10_cut01`、`この画像は物語「<topic>」の一場面`、`[物語の文脈]` のような制作管理メタ情報は blocker とする。
- scene still は後段動画の first frame 候補として読む。ただし `最初の1フレーム`、`1フレーム目`、`first frame` のような authoring metadata が prompt 本文に残っていれば blocker とする。
- mid-action / completed-action の prompt は、動画冒頭の静止画として自然に動き出せる初期状態へ書き換える指摘を出す。
- 修正方向は、内部 id を具体的な画面語へ置き換えること。例: `物語「シンデレラ」の scene10` ではなく `シンデレラの灰の台所`、`灰の残る古い台所で暖炉の灰を掃くシンデレラ`。

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
