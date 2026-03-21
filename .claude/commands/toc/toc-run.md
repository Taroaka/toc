# /toc-run

ToC（TikTok Story Creator）をトピックから実行するためのコマンド。

## 使い方（想定）

```
/toc-run "桃太郎" --dry-run
```

## 期待される出力

- `output/<topic>_<timestamp>/` が作成される
- `state.txt`（追記型）が生成される
- 成果物（`research.md` / `story.md` / `visual_value.md` / `script.md` / `video_manifest.md` 等）の本文は **日本語**で記述する（ユーザーが直接修正する前提）
- カット設計は **1カット=1ナレーション** を基本に、メイン(5–15秒) + 必要ならサブ(3–15秒)で進める（詳細は `docs/implementation/video-integration.md`）
- 音声（ナレーション）は **デフォルト必須**。意図的に作らない場合だけ `scripts/generate-assets-from-manifest.py --skip-audio` を指定する

## 方針メモ（創造と選択）

- Research は多様性（登場人物/世界観/解釈）を厚めに集め、Story でスコアが高い案を **選択**する
- Story の後に `visual_value.md` を作り、中盤に置く視覚報酬パートを設計してから Script へ渡す
- Hero's Journey への当てはめは必須ではない（フレームワークは道具）
- 矛盾する複数ソースの要素を同一シーン/設定として **混成（ハイブリッド）**する必要が出た場合は、確定前にユーザー承認を取る（運用）

詳細は `docs/how-to-run.md` を参照。
