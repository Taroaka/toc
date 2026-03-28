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
- 画像生成の review 正本は `video_manifest.md` 自体
- `review-image-prompt-story-consistency.py` は manifest を直接監査し、結果を `image_generation.review` へ書き戻してから画像生成へ進む
- review では、不足 `character_ids` の自動補完、prompt が環境寄りに流れすぎていないか、story 上の関係性/ブロッキングが抜けていないかを点検する
- `image_generation.review` は `agent_review_ok` / `agent_review_reason_keys` / `human_review_ok` / `human_review_reason` を持つ
  - 現行表記として `agent_review_reason_codes` を使っていてもよいが、意味は `agent_review_reason_keys` と同じに保つ
  - review 実行後に subagent が `agent_review_ok` を更新する
  - `human_review_ok` は初期値 `false`
  - false の cut には reason key を 1 つ以上残す
  - required block `[全体 / 不変条件]` / `[登場人物]` / `[小道具 / 舞台装置]` / `[シーン]` / `[連続性]` / `[禁止]` のいずれかが欠けていれば、subagent は `agent_review_ok: false` にする
  - この場合の canonical reason key は `missing_required_prompt_block`
  - prompt が `scene03_cut01` のような他 cut 参照や `前カット` / `次カット` / `前のprompt` のような参照依存表現を含む場合、subagent は `agent_review_ok: false` にする
  - この場合の canonical reason key は `prompt_not_self_contained`
  - prompt に `rideable` のような英語 shorthand が混ざる場合も false にする
  - この場合の canonical reason key は `non_japanese_prompt_term`
  - prompt に人物が明示されているのに `image_generation.character_ids` が空なら false にする
  - この場合の canonical reason key は `prompt_mentions_character_but_character_ids_empty`
  - false reason に対応する修正を manifest に反映し、修正後に再 review して finding が消えれば、subagent はその cut を `agent_review_ok: true` に戻す
  - `human_review_ok: true` は finding を理解して例外許容した記録であり、subagent finding を消す意味ではない
  - `human_review_ok: true` のときは `human_review_reason` を残す
  - **両方 `false` の cut が残っていると画像生成は止まる**
- 画像生成の既定サイズは `1K`（必要な scene だけ `image_generation.image_size` で上書き）
- story still の既定生成対象は `still_image_plan.mode: generate_still` のみ
  - `reuse_anchor` / `no_dedicated_still` は既定では生成しない
  - 例外的に広げるときだけ `--image-plan-modes generate_still,reuse_anchor` のように指定する
- `--apply-asset-guides --asset-guides-character-refs scene` で人物 still を回す場合、既存の `assets/characters/*_refstrip.png` は reference に自動で追加される

例（`momotaro` のマニフェストから素材生成→結合）:

```bash
python scripts/review-image-prompt-story-consistency.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --fix-character-ids

# 必要なら source manifest を修正して再 review する

python scripts/review-image-prompt-story-consistency.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --set-human-review scene02_cut01 \
  --set-human-review scene02_cut02

python scripts/generate-assets-from-manifest.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --character-reference-views front,side,back \
  --character-reference-strip \
  --image-batch-size 10 --image-batch-index 1 \
  # ナレーション音声を生成しない（意図的にサイレントで進める）場合だけ --skip-audio を付ける

# 既定値:
# - video generation は 1080p
# - provider 音声は sound off（別途 narration/BGM を render で合成）
# - 画像生成前に story/script review を自動実行し、missing character_ids は補完してから進む
# - story still は `still_image_plan.mode: generate_still` だけを既定で生成する
# - 両方 false の cut が残っていると画像生成は止まる

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
- 画像 prompt review の finding を人間判断で許容する場合は、対象 cut の `human_review_ok` を true にする
  - `human_review_ok: true` は subagent false を解消した意味ではなく、例外許容を記録しただけとみなす
  - その場合は `human_review_reason` に判断理由も残す
  - 例: `python scripts/review-image-prompt-story-consistency.py --manifest output/<topic>_<timestamp>/video_manifest.md --set-human-review scene02_cut01`

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

画像生成前レビューの成果物:

- `video_manifest.md` 内の `image_generation.review`
- `image_prompt_story_review.md`
