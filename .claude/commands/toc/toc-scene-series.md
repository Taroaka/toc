# /toc-scene-series

ToC（TikTok Story Creator）を「topic → 情報収集 → sceneごとのQ&A縦動画（複数本）」として実行するコマンド。

## 使い方（想定）

```text
/toc-scene-series "桃太郎" --min-seconds 30 --max-seconds 60
```

動画モデル指定（例: Kling）:

```text
/toc-scene-series "桃太郎" --video-tool kling --min-seconds 30 --max-seconds 60
```

部分実行（例: scene 2 と 4 だけ作り直す）:

```text
/toc-scene-series "桃太郎" --scene-ids 2,4 --min-seconds 30 --max-seconds 60
```

dry-run（外部APIは呼ばず、設計成果物まで）:

```text
/toc-scene-series "桃太郎" --dry-run
```

## 期待される出力（概要）

`output/<topic>_<timestamp>/` に以下が生成される:

- `state.txt`（追記型）
- `logs/grounding/<stage>.json`
- `research.md`
- `story.md`（questionを含む）
- `series_plan.md`（sceneごとの question 抽出）
- `scenes/sceneXX/`（sceneごとの成果物）
  - `evidence.md`
  - `script.md`（30–60秒のQ&A用）
  - `video_manifest.md`
  - `assets/**`
  - `video.mp4`
- 成果物の本文（question / ナレーション / プロンプト等）は **日本語**で記述する（ユーザーがそのまま修正できるように）
- 音声（ナレーション）は **デフォルト必須**。意図的に作らない場合だけ `scripts/generate-assets-from-manifest.py --skip-audio` を指定する

## 実行メモ（内部フローの意図）

- question は `text_overlay.sub_text` の `content` を使う
- 根拠は **既存 `research.md` 優先**、不足時のみ Web 追加調査
- scene動画の尺は **30–60秒**（内容に応じて決める）
- カット設計は **1カット=1ナレーション** を基本に、メイン(5–15秒) + 必要ならサブ(3–15秒)で分割する。`video_manifest.md` は `scenes[].cuts[]` で表現する（必要なら増減）
- 映像の「現実寄り/抽象寄り」は **実装前に再確認**（このコマンドではプレースホルダを許容）
- 方針: **創造→選択**
  - Research は多様性（登場人物/世界観/解釈）を厚めに集め、Story/Script でスコアが高い案を **選択**する
  - Hero's Journey への当てはめは必須ではない（フレームワークは道具）
  - 矛盾する複数ソースの要素を同一シーン/設定として **混成（ハイブリッド）**する必要が出た場合は、確定前にユーザー承認を取る（運用）

## Grounding Preflight（必須）

- run root の `research` / `story` / `script` 開始前に、対応する stage で `scripts/resolve-stage-grounding.py` を実行する
- scene root の `image_prompt` / `video_generation` に進む前も同様に preflight を通す
- 証跡は `logs/grounding/<stage>.json`
- 各 resolve の直後に `scripts/audit-stage-grounding.py` で readset / audit を確定する
- `stage.<name>.grounding.status=ready` と `stage.<name>.audit.status=passed` が確認できない場合は、その stage を開始しない

## 参照

- 既存エントリ: `.claude/commands/toc/toc-run.md`
- 設計: `.steering/20260125-scene-series/requirements.md`
- 仕様（正本）: `docs/implementation/scene-series-entrypoint.md`
