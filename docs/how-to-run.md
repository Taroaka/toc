# How to Run (MVP)

本書は `todo.txt` の 15) Documentation に対応する。

## 前提
- 起点は Claude Code の slash command（例: `/toc-run`, `/toc-scene-series`, `/toc-immersive-ride`）
- 成果物は `output/<topic>_<timestamp>/` に生成される
- 成果物（`research.md` / `story.md` / `script.md` / `video_manifest.md` 等）の本文は **日本語**で記述する（ユーザーがそのまま修正できるように）
  - 例外: ツール名 / ファイルパス / コード / 固有名詞はそのまま（必要なら英語併記はOK）
- state は `output/<topic>_<timestamp>/state.txt`（追記型）
- 方針: **創造→選択**
  - Research は多様性（登場人物/世界観/解釈）を厚めに集め、Story/Script でスコアが高い案を選択する
  - 矛盾する複数ソースの要素を同一シーン/設定として混成（ハイブリッド）する必要が出た場合は、確定前にユーザー承認を取る（運用）

## セットアップ（Docker）

1) `.env.example` を `.env` にコピーし、APIキー等を設定する  
2) 起動:

```bash
docker-compose up --build
```

## セットアップ（uv / local）

uv で依存を揃える場合（.venv を作って同期）:

```bash
python -m pip install -U uv
scripts/uv-sync.sh
```

## 実行（想定）

Claude Code で以下を実行:

```
/toc-run "桃太郎" --dry-run
```

YouTube サムネイル用の prompt だけ作る場合:

```text
/toc-youtube-thumbnail "桃太郎"
```

既存 run dir を参照して、作品内容に寄せたサムネ prompt を作る場合:

```text
/toc-youtube-thumbnail "浦島太郎" --run-dir output/浦島太郎_<timestamp>
```

sceneごとにQ&A動画を複数本作る場合:

```
/toc-scene-series "桃太郎" --min-seconds 30 --max-seconds 60
```

シーンエージェント（multi-agent）で scene-series の下準備を行う場合:

```bash
python scripts/ai/toc-scene-series-multiagent.py "桃太郎" --min-seconds 30 --max-seconds 60
python scripts/toc-scene-series.py "桃太郎" --run-dir output/桃太郎_<timestamp>
```

没入型（実写シネマティック体験）の単発動画:

```text
/toc-immersive-ride --topic "桃太郎"
```

## 期待される出力（/toc-run）

```
output/<topic>_<timestamp>/
  state.txt
  research.md
  story.md
  script.md
  video_manifest.md
  video.mp4          (プレースホルダでも可)
  run_report.md
  logs/
```

## 期待される出力（/toc-scene-series）

```
output/<topic>_<timestamp>/
  state.txt
  research.md
  story.md
  series_plan.md
  scenes/
    scene01/
      evidence.md
      script.md
      video_manifest.md
      assets/
      video.mp4
    scene02/
      ...
```

## 生成（画像/動画/TTS）について

- 画像: Google Nano Banana Pro（Gemini Image / `gemini-3-pro-image-preview`）
- 画像（代替）: SeaDream / Seedream 4.5（`tool: "seadream"` + `SEADREAM_*`）
- 動画: Kling 3.0（default。`video_generation.tool: "kling_3_0"` + `KLING_ACCESS_KEY`/`KLING_SECRET_KEY`）
- 動画（Omni）: Kling 3.0 Omni（`video_generation.tool: "kling_3_0_omni"` + `KLING_OMNI_*`）
- 動画（代替）: Seedance（BytePlus ModelArk。`video_generation.tool: "seedance"` + `ARK_API_KEY`）
- ※ Google Veo はこのリポジトリでは安全のため無効化（Veo系の tool 名は Kling にルーティング）
- TTS: ElevenLabs
- 当面は `video_manifest.md` を入力に素材生成→結合でフローを検証する
- 具体は `docs/implementation/video-integration.md` を参照
- 画像生成は `video_manifest.md` 直読みではなく、`export-image-prompt-collection.py` で prompt collection を切り出してレビューしてから回す

例（`momotaro` のマニフェストから素材生成→結合）:

```bash
python scripts/export-image-prompt-collection.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md

python scripts/generate-assets-from-manifest.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --character-reference-views front,side,back \
  --character-reference-strip \
  --image-batch-size 10 --image-batch-index 1 \
  # ナレーション音声を生成しない（意図的にサイレントで進める）場合だけ --skip-audio を付ける

# 既定値:
# - video generation は 1080p
# - provider 音声は sound off（別途 narration/BGM を render で合成）

python scripts/build-clip-lists.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --out-dir output/momotaro_20260110_1700

scripts/render-video.sh \
  --clip-list output/momotaro_20260110_1700/video_clips.txt \
  --narration-list output/momotaro_20260110_1700/video_narration_list.txt \
  --out output/momotaro_20260110_1700/video.mp4
```

## state運用

- `state.txt` は追記型（最新ブロックが現在状態）
- 擬似ロールバックは「過去ブロックのコピーを末尾に追記」で再現する
- スキーマは `workflow/state-schema.txt` を参照
- 物語の矛盾ソースを同一シーン/設定として混成（ハイブリッド）する場合は、確定前に人間承認を取る（運用）
  - 承認: `python scripts/toc-state.py approve-hybridization --run-dir output/<topic>_<timestamp> --note "OK"`

## verify

run ごとの標準 verify:

```bash
python scripts/verify-pipeline.py \
  --run-dir output/<topic>_<timestamp> \
  --flow toc-run|scene-series|immersive \
  --profile fast|standard
```

生成物:

- `run_status.json`
- `eval_report.json`
- `run_report.md`
