# Video Integration（正本）

このドキュメントは `.steering/20260117-video-integration/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

`script.md` から素材生成→合成→検証までを一貫した流れとして定義する。

## 全体フロー

`script.md → video_manifest.md → assets生成 → clips/narration list → render-video.sh → video.mp4 → QA`

## Scene → Assets 契約（最小）

入力（scene単位）:
- `scene_id`
- `narration_text`
- `visual_prompt`
- `duration_seconds`
- `constraints`
  - （任意）参照画像: `references[]`
  - （任意）動画の開始/終了フレーム: `first_frame`, `last_frame`

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

分割判断:
- 15秒を超えそうなら、役割が近いカットを 2 本以上に分割する
- 15秒以下でも、scene と narration の両方が揃った時点で「分割した方が映像として自然か」を都度判断する

運用（例）:
1) `video_manifest.md` を cuts 前提で書く（`scenes[].cuts[]` でも、sceneをカットとして扱ってもよい）
2) 先に音声だけ生成して秒数を確定する（audio-only）
   - `python scripts/generate-assets-from-manifest.py --manifest output/<run>/video_manifest.md --skip-images --skip-videos`
3) `video_generation.duration_seconds` をナレーション秒数に合わせて更新し、その後に画像/動画生成に進む

注意:
- `cloud_island_walk`（哲学を島でPOV視点で語る体験）の指示・テンプレは別仕様として扱う（この運用変更の対象外）。

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
