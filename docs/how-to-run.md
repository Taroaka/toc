# How to Run (MVP)

本書は ToC の通常実行手順を定義する。production は直接 authoring → ordinary structural
validation → generation の順で進む。source、schema、ID、参照、request、file、decode、duration、
audio/video、provenance の検証は必須で、production の品質採点や別の合格証明は使わない。

## 前提

- 起点は Codex assistant command（Claude Code slash command 互換）。
- 成果物は `output/<topic>_<timestamp>/` に保存する。
- run の `state.txt` は append-only。
- 本文 artifact は原則日本語で書き、tool 名、path、code、固有名詞は必要に応じて原文を使う。
- source の exact bytes、topic、experience、target duration を
  `logs/orchestration/create_input.json` に保存してから authoring を始める。
- contradictory source variants の hybridization は明示したユーザー選択として保存する。

## セットアップ

Docker:

```bash
docker-compose up --build
```

uv/local:

```bash
python -m pip install -U uv
scripts/uv-sync.sh
```

## 基本実行

```text
/toc-run "桃太郎" --dry-run
/toc-immersive-ride --topic "桃太郎"
/toc-scene-series "桃太郎" --min-seconds 30 --max-seconds 60
```

p 番号の coarse target は bucket 最後の active slot まで実行する。

```text
/toc-immersive-ride --topic "かぐや姫" --stage p300 --experience cinematic_story
/toc-immersive-ride --topic "かぐや姫" --stage 300 --experience cinematic_story
/toc-world-walk --source-run output/桃太郎_<timestamp>
```

active target map:

```text
p100→p120  p200→p220  p300→p330  p400→p450  p500→p570
p600→p680  p700→p750  p800→p860  p900→p920
```

実際の active slots は p110/p120、p210/p220、p310/p330、p410/p420/p440/p450、
p510/p520/p530/p550/p560/p570、p610/p620/p650/p660/p670/p680、
p710/p730/p740/p750、p810/p830/p840、p910/p920 である。

YouTube thumbnail prompt:

```text
/toc-youtube-thumbnail "桃太郎"
/toc-youtube-thumbnail "浦島太郎" --run-dir output/浦島太郎_<timestamp>
```

## Frontend create をヘッドレスで確認する

フロントの作成ボタンと同じ endpoint を使う。

```bash
python scripts/toc-create-run-headless.py \
  --title "シンデレラ" \
  --source "シンデレラ" \
  --no-images
```

画像を生成する場合は `--no-images` を省略する。実 server に送る場合:

```bash
python scripts/toc-create-run-headless.py \
  --title "シンデレラ" \
  --source "シンデレラ" \
  --base-url "http://127.0.0.1:8000" \
  --no-images
```

結果は run の ordinary execution report と `state.txt` に保存される。frontend と CLI は同じ
source, compiler, request snapshot, provider, structural validator を使う。

## 期待される出力

```text
output/<topic>_<timestamp>/
  p000_index.md
  state.txt
  research.md
  story.md
  visual_value.md
  script.md
  video_manifest.md
  asset_inventory.md
  asset_plan.md
  assets/
  audio/
  video.mp4
  logs/grounding/
  logs/orchestration/
```

scene-series は run 内に `scenes/sceneXX/` を持ち、各 scene に evidence、script、manifest、
assets、video を置く。

## Stage context

各 stage で次を行う。

```bash
python scripts/prepare-stage-context.py \
  --stage research|story|script|narration|asset|scene_implementation|video_generation|render|qa \
  --run-dir output/<topic>_<timestamp> \
  --flow toc-run|scene-series|immersive
```

返された source/readset の順序 `global_docs → stage_docs → templates → inputs` で読み、
canonical artifact を author する。その後、対応する普通の structural validator、request
validator、output/provenance validator を実行する。source/readset が欠けていれば入力不足として
停止する。

## 生成 providers

- 画像: Codex built-in image generation（`codex_builtin_image` / `gpt-image-2`）
- 動画: Kling 3.0（`kling_3_0`）、Kling 3.0 Omni、または Seedance
- TTS: ElevenLabs
- provider は request metadata と compiler で指定し、provider-facing prompt に制作管理メタを
  混ぜない。
- 画像 request は reference count、execution lane、request snapshot、source digest、
  reference bytes hash を保存する。
- 画像/動画は provider の実際の response item、prompt hash、reference hash、destination が
 一致した場合だけ run output に copy する。
- local placeholder、未署名の別 request の画像、存在しない reference、decode 不能 output は
  canonical output として採用しない。

## Authoring → validation → generation

```text
research.md
  → story.md
  → visual_value.md
  → script.md + video_manifest.md (manifest_phase: skeleton)
  → asset_inventory.md + asset_plan.md + asset requests
  → production manifest + image requests
  → image generation and file/provenance checks
  → narration/TTS + measured duration
  → video requests + clip generation
  → stream normalization + final render
  → ordinary QA data
```

`p410` は scene intent/event sequence、`p420` は cut blueprint の authoring slot である。
cut は event beat、first frame、motion boundary、narration boundary、asset dependency、handoff を
持ち、構造 validator が exact ID と順序を確認する。target duration の割り算だけで scene/cut を
水増ししない。

### 画像

`scene_event → cut_contract → first_frame_visual_plan → drawable_prompt_ir →
image_generation.api_prompt_payload` の一方向 compiler を使う。provider には drawable な現在状態、
許可された motion constraints、provider settings だけを送る。request snapshot の prompt、hash、
reference bindings、destination は provider 呼び出し前後で一致させる。

### ナレーション

`script.md` が narration source of truth で、`tts_text` は TTS 用 projection である。
pronunciation dictionary、candidate listening、text editing は任意の user choice。TTS output は
実測 duration と decode を確認し、intentional silence には reason、duration、確認 actor を持たせる。
audio timeline は spoken audio と明示した silence を合計し、video timeline と混同しない。

### 動画

保存済み compiled motion payload を使い、first/last frame、ordered references、provider settings、
prompt hash、source digest を request に束縛する。未 materialize、current design drift、reference
bytes drift、provider option drift は stale request として拒否する。

## Optional user actions

candidate の選択、音声の listening、画像の編集、narration の編集、change request は任意である。
選択/編集を `human_choice.*` として保存し、変更後の request revision を再検証してから生成する。
hybridization は `toc-state.py approve-hybridization` など明示操作で記録する。publication は生成
とは別の明示ユーザー操作である。

## State と resume

state の確認:

```text
status=IMAGE
stage.asset.status=done
stage.scene_implementation.status=in_progress
slot.p660.status=in_progress
request.scene01_cut01.status=generated
output.scene01_cut01.provenance_status=matched
```

resume は state history を書き換えず、upstream digest が変わった downstream item だけを stale と
して再 materialize/再生成する。valid output は binding が一致する限り保持する。run lease と
destination lock を使い、同じ run を二つの process で mutate しない。

## Ordinary verification

```bash
python scripts/verify-pipeline.py \
  --run-dir output/<topic>_<timestamp> \
  --flow toc-run|scene-series|immersive \
  --profile fast|standard
```

確認対象:

- required artifact と fixed slot state
- YAML/JSON/Markdown schema、type、unique ID、reference、selector closure
- manifest/request/prompt/source/provider hash の一致
- generated file existence、file type、decode、duration、audio/video stream
- request-bound provenance と destination lock
- final render の ffprobe、aspect ratio、audio sync、subtitle files

`run_report.md` や `eval_report.json` が存在する古い run は入力として読めるが、現在の stage の
進行条件ではない。新しい run は必要な ordinary execution data と `p000_index.md` を生成する。

## Hybridization and publishing

```bash
python scripts/toc-state.py approve-hybridization \
  --run-dir output/<topic>_<timestamp> \
  --note "ユーザーが明示した選択"
```

source variant、選択 actor、時刻、publication target、publish result は run artifact に保存する。


## p860 BGM・SE

動画生成後、フロントの「BGM・SE」で動画を承認し、候補案を編集・生成・試聴して採用する。音量・開始位置・fade・loopを保存し、設定を確定してから最終結合へ進む。追加音が不要なら「BGM・SEなしで確定」を選ぶ。[仕様](implementation/sound-design.md)。
