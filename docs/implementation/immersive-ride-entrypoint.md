# Entrypoint（/toc-immersive-ride）仕様（正本）

このドキュメントは `.steering/20260131-immersive-ride/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

Claude Code の slash command を起点に、最小限の入力（topic）で
「没入型（実写シネマティック体験）」動画を **1本**生成する。
（視点は experience / scene の意図に応じて選び、必ずしも一人称POVに固定しない）

## 仕様（想定）

- コマンド: `/toc-immersive-ride`
- 引数:
  - `--topic`（必須）
  - `--dry-run`（任意。外部生成APIは呼ばない）
  - `--config`（任意。`config/system.yaml` を差し替え）
  - `--experience`（任意。default: `cloud_island_walk`）
    - `cinematic_story`: 物語を映画的に見せる（視点は必要に応じて。固定デバイスを前提にしない）
    - `cloud_island_walk`: 雲上の島を歩いて理解を深める（哲学/概念の比喩）パターン
    - `ride_action_boat`: 互換用の legacy 名（内部的には `cinematic_story` 扱い）

## 挙動（成果物）

run root:

- `output/<topic>_<timestamp>/`
  - `state.txt`（追記型）
  - `research.md`
  - `story.md`
  - `visual_value.md`
  - `script.md`（言語情報の正本）
  - `video_manifest.md`
  - `assets/**`
  - `video.mp4`（完成。1280x720 / 24fps）

## 表現の固定条件（experience別）

共通（必須）:

- 視点: scene の意図に応じて **POV / 三人称** を選んでよい（ただし 1カット内で視点ブレさせない）
- Style: photorealistic / cinematic / practical effects（アニメ調排除）
- 映像内の文字は禁止（画面内テキスト/字幕/ウォーターマーク/ロゴ）
- ガイドは音声（ナレーション）として必須（視覚的に登場させない）

`cinematic_story`:

- 統一要素:
  - 視点は必要に応じて（POV固定にしない）
  - 固定の乗り物/デバイスを前景アンカーにしない
  - 物語キャラクター / 主役級アイテム（例: 玉手箱）をアンカーにして連続性を作る（照明/色/構図も含む）
  - story scene は **10刻み**（10,20,30...）で振る
  - `scene_id: 0` の character_reference は別枠として扱い、**全身（頭からつま先まで）** の参照に限定する

`cloud_island_walk`（default）:

- 統一要素（推奨）:
  - 手元の“アンカー”（例: compass / journal）を前景に置き、POVの安定を作る
  - 島の各ゾーンを“概念の比喩（物理メタファ）”として設計する（文字で説明しない）
  - 道/橋/階段など「前進の導線」が常に画面にある（scene間の連続性を作る）

## 生成設計（最小）

- 画像:
  - 参照画像（キャラクター/重要小道具）を **必要なscene** に適用（必要なら scene 側で `references` を指定）
  - 16:9 / 1K（素材側の既定。必要な scene だけ個別に引き上げる）
- 動画:
  - provider は `video_manifest.md` の `scenes[].video_generation.tool` で選ぶ（default: `kling_3_0` / alt: `seedance`）
  - 注: Google Veo は安全のためこのリポジトリでは無効化している
  - first-last-frame-to-video
  - 8秒/clip
  - scene画像の **manifest順** をつないでclipを作る（scene_id の連番を前提にしない）
  - シームレス性を上げるため、best-effort で以下を併用する
    - `last_frame` 制約（`--enable-last-frame`）
    - ネガティブプロンプトでフェード/カット系を抑制（`--video-negative-prompt`）
    - 直前clip終盤のフレームを次clipの first frame に使う chaining（`--chain-first-frame-from-prev-video`）
- 音声:
  - ElevenLabs（voice/model は運用で確定）
  - **1カット=1ナレーション**（`audio.narration.output` は cut/clip ごとに分割）
  - `audio.narration.text` は物語原稿、`audio.narration.tts_text` は ElevenLabs に送るひらがな原稿として Narration Writer が確定する（`TODO:` 等のメタ情報は入れない）
  - 先に音声だけ生成し、実秒から `duration_seconds` / `timestamp` を同期してから映像生成に進む
  - 反復中に意図的に音声を省略してサイレントで進める場合のみ `--skip-audio` を使う
  - 例外として、`visual_value.md` に基づく silent cut は `audio.narration.tool: "silent"` と `text: ""` を許可する

## コスト最適化（任意）

- Seedance を使う場合は `ARK_SEEDANCE_*_MODEL` を運用で切り替える
- Kling を使う場合は `KLING_VIDEO_MODEL` / `KLING_OMNI_VIDEO_MODEL` を運用で切り替える

## state（追記）

`state.txt` に追記（例）:

- `runtime.stage=research|story|script|manifest|assets|render|done`
- `runtime.stage=research|story|visual_value|script|manifest|assets|render|done`
- `runtime.render.status=started|success|failed`
- `artifact.video=output/<topic>_<timestamp>/video.mp4`
- `review.video.status=pending|approved|changes_requested`（最終判断は人間）

人間の承認（例）:

```bash
python scripts/toc-state.py approve-video --run-dir output/<topic>_<timestamp> --note "OK"
```

## 参照

- `.claude/commands/toc/toc-immersive-ride.md`
- `docs/how-to-run.md`
- `docs/implementation/video-integration.md`

## scene_id の運用（推奨）

- **最初から 10 刻み**で振る（例: 10, 20, 30, 40, ...）
  - 後から中間シーンを差し込みたい時に `15` や `35` のように追加できる
  - 後段処理は **scene_id の連番** を前提にしない（manifest順を正とする）
- ただし `scene_id: 0` の character_reference は story scene とは別枠で固定する
