# Video Integration（正本）

このドキュメントは `.steering/20260117-video-integration/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

`script.md` から素材生成→合成→検証までを一貫した流れとして定義する。

## 全体フロー

`script.md → video_manifest.md → assets生成 → clips/narration list → render-video.sh → video.mp4 → QA`

## 正本ルール

- **`script.md` を言語情報の正本**とする
- `audio.narration.text` は `script.md` の narration を平易化したものであり、別の話を足さない
- `image_generation.prompt` / `video_generation.motion_prompt` は `script.md` の visual beat を生成向けに翻訳したものであり、新しい物語情報を足さない
- `scene_conte.md` は橋渡し資料であり、`script.md` と矛盾してはならない

## 映像とナレーションの役割分担

- 原則: **見えることは映像にやらせる**
- ナレーションは **見えないが重要なこと** を補う
- 目標は、ナレーションが無くても scene の大意が通ること。その上で音声が理解の方向・因果・内面・時間を足すこと
- ナレーションは映像の説明文ではなく、観客の認知の導線を整える層として扱う

ナレーションが優先して運ぶ情報:
- 時間の圧縮 / 回想 / 予感
- 内面（迷い、願い、後悔、決意）
- 因果（なぜそうしたか / 次に何が効いてくるか）
- 視点の偏り
- 世界のルール / 禁忌 / 伝承
- 終盤の軽い意味づけ

まず映像に任せる情報:
- 一目で分かる物理行動
- 一目で分かる感情
- 空間の基本説明
- 画面構図だけで読める力関係や距離感

## Scene → Assets 契約（最小）

入力（scene単位）:
- `scene_id`
- `narration_text`
- `visual_prompt`
- `duration_seconds`
- `constraints`
  - （任意）参照画像: `references[]`
  - （任意）動画の開始/終了フレーム: `first_frame`, `last_frame`

補足:
- ここでの参照画像は、毎sceneの必須成果物ではない
- 新規の静止画生成は、連続性アンカーを作るとき、または同じ場所/物体/人物状態を複数scene/cutで再利用するときに優先する
- それ以外の scene/cut は、既存の anchor frame を再利用してよい

出力（scene単位）:
- `assets/scenes/scene{n}_base.png`
- `assets/scenes/scene{n}_video.mp4`
- `assets/audio/scene{n}_narration.mp3`

記録先:
- `video_manifest.md` の `scenes[]`

## Cut（カット）設計: ナレーション起点（推奨）

基本:
- **1カット = 1ナレーション**
- **メインカット**（最低1つ）: **5–15 秒**
- **サブカット**（任意 / 複数可）: **3–15 秒**
  - 1ナレーション=1カットのとき、3秒のカットは通常使わない（最短は5秒）
  - 複数カットに分割できる場合のみ、短尺（3–4秒）を **サブカット**として選択できる
- 例外:
  - `visual_value.md` に基づく **視覚報酬カット** は、**4秒固定 / ナレーションなし** を許可する
  - この場合は `audio.narration.tool: "silent"` と `audio.narration.text: ""` を使う

分割判断:
- 15秒を超えそうなら、役割が近いカットを 2 本以上に分割する
- 15秒以下でも、scene と narration の両方が揃った時点で「分割した方が映像として自然か」を都度判断する

運用（例）:
1) `video_manifest.md` を cuts 前提で書く（`scenes[].cuts[]` でも、sceneをカットとして扱ってもよい）
   - `audio.narration.text` は **空文字**でよい（未記入）。`TODO:` のようなメタ情報は入れない（TTSで喋られて事故る）
2) Narration Writer が `audio.narration.text`（読み上げ原稿）を確定する
  - 原稿は平易で寄り添う話し言葉を優先し、文末は原則 `です・ます調` にする
  - 各行は、映像だけでは取り切れない情報を最低1つ足す
    - 例: 時間 / 内面 / 因果 / 視点 / 禁忌 / 軽い意味づけ
  - 画面に見えている行動の単純な言い換えは避け、映像との関係は「説明」より「補完」を優先する
  - `script.md` の `scene_summary` は先の展開を匂わせすぎず、今その scene で起きることを素直に要約する
  - `script.md` の `visual_beat` は概要確認用の平文とし、カメラ/レンズ/構図などの制作語は入れない
   - 深い設計意図や抽象テーマは、基本的にナレーションで説明せず映像側へ置く
   - 終盤の学び/余韻パートだけ、満足感のために軽く言語化してよい
   - `script.md` に無い情報や、映像制作用のカメラ専門語は原則入れない
3) 先に音声だけ生成して秒数を確定する（audio-only）
   - `python scripts/generate-assets-from-manifest.py --manifest output/<run>/video_manifest.md --skip-images --skip-videos`
4) `video_generation.duration_seconds` をナレーション秒数に合わせて更新し、その後に画像/動画生成に進む
   - `python scripts/sync-manifest-durations-from-audio.py --manifest output/<run>/video_manifest.md`

silent cut の扱い:

- `audio.narration.tool: "silent"` の cut は、Narration Writer の対象外としてよい
- その場合でも `audio.narration.output` は持たせ、無音 mp3 を生成できる状態にする
- `video_generation.duration_seconds` は `4` 秒を基本にする

### 尺の決め方（音声実秒 + 余白）

- 原則として、**`映像尺 = 音声実秒 + 余白`** とする
- `音声秒 = 映像秒` にぴったり合わせるのは標準運用にしない
- 余白は、話し始め前の入りと、話し終わり後の余韻の合計として扱う

推奨レンジ:
- 通常 cut:
  - 前余白: `0.2–0.5秒`
  - 後余白: `0.3–1.0秒`
  - 合計: `0.5–1.5秒`
- 余韻重視 cut:
  - 合計: `1.0–2.0秒`
- テンポ重視 / サブ cut:
  - 合計: `0.3–0.7秒`

運用順:
1. まず自然長で TTS を生成する
2. `ffprobe` 等で音声の実秒を測る
3. cut の役割に応じた余白を足して `video_generation.duration_seconds` を決める
4. その結果が `main 5–15秒 / sub 3–15秒` を外れる場合だけ、原稿短縮または cut 再設計を行う

補足:
- 聞き比べテストなどで `--duration-seconds` を使って音声を固定長にそろえることはあるが、これは比較用の例外運用であり、実制作の標準ではない

注意:
- `cloud_island_walk`（哲学を島でPOV視点で語る体験）の指示・テンプレは別仕様として扱う（この運用変更の対象外）。

## ナレーション密度の目安

- 映画的・没入型を優先する場合:
  - 映像/演出/効果音: 70–85%
  - ナレーション: 15–30%
- 神話・歴史・昔話・伝承紹介型:
  - 映像: 55–70%
  - ナレーション: 30–45%

これは固定法則ではなく、初期設計の目安として使う。

## プレースホルダ（MVP）

プロバイダは当面、manifestで選べる（例: Google Gemini Image / Seedance / Kling 3.0）。ただしMVPでは:

- placeholder でE2Eを通す（`scripts/generate-placeholder-assets.py`）
- 生成APIで素材化する（`scripts/generate-assets-from-manifest.py`）

注: Google Veo はこのリポジトリでは安全のため無効化している。

## 品質ゲート（最小）

- `duration_ok`
- `aspect_ratio_ok`
- `audio_sync_ok`
- `subtitle_ok`

結果は `state.txt` と `video_manifest.md` に記録する。

## 参照

- `docs/video-generation.md`
- `scripts/build-clip-lists.py`
- `scripts/render-video.sh`
