# /toc-run

ToC（TikTok Story Creator）をトピックから実行するためのコマンド。

## 使い方（想定）

```
/toc-run "桃太郎" --dry-run
```

## 期待される出力

- `output/<topic>_<timestamp>/` が作成される
- `state.txt`（追記型）が生成される
- `logs/grounding/<stage>.json` に stage ごとの参照証跡が残る
- 成果物（`research.md` / `story.md` / `visual_value.md` / `script.md` / `video_manifest.md` 等）の本文は **日本語**で記述する（ユーザーが直接修正する前提）
- カット設計は **1カット=1ナレーション** を基本に、メイン(5–15秒) + 必要ならサブ(3–15秒)で進める（詳細は `docs/implementation/video-integration.md`）
- 音声（ナレーション）は **デフォルト必須**。意図的に作らない場合だけ `scripts/generate-assets-from-manifest.py --skip-audio` を指定する

## 方針メモ（創造と選択）

- Research は多様性（登場人物/世界観/解釈）を厚めに集め、Story でスコアが高い案を **選択**する
- Story の後に `visual_value.md` を作り、中盤に置く視覚報酬パートを設計してから Script へ渡す
- Hero's Journey への当てはめは必須ではない（フレームワークは道具）
- 矛盾する複数ソースの要素を同一シーン/設定として **混成（ハイブリッド）**する必要が出た場合は、確定前にユーザー承認を取る（運用）

## Grounding Preflight（必須）

- `research` 開始前:
  - `python scripts/resolve-stage-grounding.py --stage research --run-dir output/<topic>_<timestamp> --flow toc-run`
- `story` 開始前:
  - `python scripts/resolve-stage-grounding.py --stage story --run-dir output/<topic>_<timestamp> --flow toc-run`
- `script` 開始前:
  - `python scripts/resolve-stage-grounding.py --stage script --run-dir output/<topic>_<timestamp> --flow toc-run`
- 画像 prompt / 動画生成へ進む前:
  - `python scripts/resolve-stage-grounding.py --stage image_prompt --run-dir output/<topic>_<timestamp> --flow toc-run`
  - `python scripts/resolve-stage-grounding.py --stage video_generation --run-dir output/<topic>_<timestamp> --flow toc-run`
- 各 resolve の直後に `python scripts/audit-stage-grounding.py --stage <stage> --run-dir output/<topic>_<timestamp>` を実行する
- `stage.<name>.grounding.status=ready` と `stage.<name>.audit.status=passed` を確認できない限り、その stage を開始しない

詳細は `docs/how-to-run.md` を参照。
