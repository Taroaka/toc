# /toc-youtube-thumbnail

ToC（TikTok Story Creator）の物語動画に対して、YouTube サムネイル用の構造化プロンプトを返すコマンド。

## 使い方（想定）

物語名だけで作る場合:

```text
/toc-youtube-thumbnail "桃太郎"
```

既存 run dir を参照して作る場合:

```text
/toc-youtube-thumbnail "浦島太郎" --run-dir output/浦島太郎_20260321_1530
```

## 期待される出力

- ユーザーへ返す構造化テキスト
  - `story_title`
  - `thumbnail_goal`
  - `canvas`
  - `text_design`
  - `background_direction`
  - `composition`
  - `quality_constraints`
  - `avoid`
  - `final_prompt`
- 画像生成 API は呼ばない
- `final_prompt` は、そのまま画像生成ツールへ貼れる完成形にする

## 内部フローの意図

- エージェントは `.claude/agents/youtube-thumbnail-prompt-writer.md` を使う
- 入力の優先順位:
  1. ユーザー指定の物語名
  2. `--run-dir` で指定された既存成果物
  3. `story.md` / `visual_value.md` / `video_manifest.md`
  4. 成果物が無ければ物語名から一般的モチーフを推定
- 文字は必ず大きく、既成フォントではなく物語イメージから発想した装飾文字にする
- 背景は物語世界を伝えるが、文字可読性を壊さない
- YouTube thumbnail 向けに `16:9`、`1280x720` 以上、高コントラスト、スマホ一覧での視認性を明記する

## 実行メモ

- `output/<topic>_<timestamp>/` が存在すれば、その作品の `visual_value.md` や `video_manifest.md` のモチーフを優先して背景へ反映する
- run dir が無い場合でも、昔話の代表的モチーフから成立する prompt を返す
- デフォルトではファイル保存しない。必要なら別途 `thumbnail_prompt.md` などへ保存する運用を追加する

## 参照

- エージェント定義: `.claude/agents/youtube-thumbnail-prompt-writer.md`
- 実行方法の正本: `docs/how-to-run.md`
- 役割定義の正本: `docs/implementation/agent-roles-and-prompts.md`
