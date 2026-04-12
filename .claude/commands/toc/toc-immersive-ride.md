# /toc-immersive-ride

ToC（TikTok Story Creator）で「没入型（実写シネマティック体験）」動画を単発で生成するコマンド。

## 使い方（想定）

```text
/toc-immersive-ride --topic "桃太郎"
```

哲学的な概念を「雲上の島を歩いて理解を深める」パターンで作る場合:

```text
/toc-immersive-ride --topic "自由意志" --experience cloud_island_walk
```

台本/マニフェストまでで止めたい場合:

```text
/toc-immersive-ride --topic "桃太郎" --stage script
```

## コンセプト（experience別）

共通:

- 視点は scene の意図に応じて（POV/三人称）。ただし 1カット内で視点ブレさせない
- 実写風シネマティック（photorealistic / cinematic / practical effects）
- ガイドは **音声（ナレーション）として必須**（視覚的に登場させない）

`cinematic_story`:

- 統一要素:
  - 視点は必要に応じて（POV固定にしない）
  - ボート/真鍮バー/手元アンカーなどの “固定デバイス” は使わない
  - 物語キャラクター / 主役級アイテム（例: 玉手箱）をアンカーにして連続性を作る
  - 物語キャラクター（毎scene必ず登場）
  - 音声は **1カット=1ナレーション** を基本にする（メイン=5–15秒、サブ=3–15秒）

`cloud_island_walk`（default）:

- 「雲の上に浮かぶ島（概念の楽園）」に到着し、歩みを進めるほど理解が深まる構成
- 統一要素（推奨）:
  - 島の各ゾーンを“概念の比喩（物理メタファ）”として設計する（文字で説明しない）
  - 道/階段/橋など「前進の導線」が常に画面にある（scene間の連続性を作る）
  - POV の連続性は構図で固定する（地平線の安定、path/leading lines をセンター、一定のカメラ高さ）

## 期待される出力（概要）

`output/<topic>_<timestamp>/` に以下が生成される:

- `state.txt`（追記型）
- `logs/grounding/<stage>.json`
- `research.md`
- `story.md`
- `visual_value.md`
- `script.md`
- `video_manifest.md`
- `assets/**`
- `video.mp4`（完成動画。1280x720 / 24fps）
- 成果物（`research.md` / `story.md` / `visual_value.md` / `script.md` / `video_manifest.md` / `scene_conte.md` 等）の本文は **日本語**で記述する（ユーザーが直接修正する前提）

## 実行フロー（内部の意図）

```text
topic
  → Deep Research（deep-researcher）
  → Story（director）
  → Visual Value（visual-value-ideator）
  → Script + Manifest（immersive-scriptwriter）
  → Generate assets（API）
  → Render final video（ffmpeg）
```

各 stage 開始前に `python scripts/resolve-stage-grounding.py --stage research|story|script|image_prompt|video_generation --run-dir output/<topic>_<timestamp> --flow immersive` を実行し、その直後に `python scripts/audit-stage-grounding.py --stage <stage> --run-dir output/<topic>_<timestamp>` を実行する。`stage.<name>.grounding.status=ready` と `stage.<name>.audit.status=passed` を確認してから進める。

## 方針メモ（創造と選択 / 混成承認）

- Research は多様性（登場人物/世界観/解釈）を厚めに集め、Story でスコアが高い案を **選択**する
- Story の後に `visual_value.md` を作り、動画生成AIで最も価値が出る中盤パートを抽出してから Script へ渡す
- 価値パートは原則として `20% - 80%` に置き、`4-6` カット、各 `4` 秒、ナレーションなしを基本にする
- Hero's Journey への当てはめは必須ではない（フレームワークは道具）
- 複数ソースの矛盾を、同一シーン/設定として **混成（ハイブリッド）**しない（破綻しやすい）
  - どうしても混成がスコアに効く場合は、確定前にユーザー承認を取る（衝突点・混ぜたい要素・リスクと安全策を提示して Yes/No）

## 引数

$ARGUMENTS:
- `--topic "<topic>"` (required)
- `--stage video|script` (optional, default: `video`)
  - `video`: 完成動画まで生成する（API + ffmpeg を含む）
  - `script`: `research.md` / `story.md` / `script.md` / `video_manifest.md` まで作って止める
- `--experience cinematic_story|cloud_island_walk|ride_action_boat` (optional, default: `cloud_island_walk`)
  - `cinematic_story`: 物語を映画的に見せる（ボート/真鍮バーの固定仕様は使わない）
  - `cloud_island_walk`: 雲上の島を歩いて理解を深める（哲学/概念の比喩）パターン
  - `ride_action_boat`: legacy 名（互換用。内部的には `cinematic_story` 扱い）
- `--video-tool kling|kling-omni|seedance|veo` (optional, default: `kling-omni`)
  - `kling`: `video_manifest.md` の `scenes[].video_generation.tool` を `kling_3_0` にする
  - `kling-omni`: `video_manifest.md` の `scenes[].video_generation.tool` を `kling_3_0_omni` にする
  - `seedance`: `video_manifest.md` の `scenes[].video_generation.tool` を `seedance` にする
  - `veo`: 安全のためこのrepoでは無効化（`kling_3_0_omni` に置換する）

## 実行手順（このコマンドが実行すること）

1) run dir を作成する（`output/<topic>_<timestamp>/`）
   - `<timestamp>` は `YYYYMMDD_HHMM` を使う
2) run dir に `state.txt`（追記型）を作成し、`runtime.stage=init` を追記する
3) Deep Research（エージェント: `deep-researcher`）
   - 出力先は run dir の `research.md` とする（`output/research/` だけに出して終わらない）
4) Story（エージェント: `director`）
   - 入力: `research.md`
   - 出力: `story.md`
5) Visual Value（エージェント: `visual-value-ideator`）
   - 入力: `research.md` + `story.md`
   - 出力: `visual_value.md`
6) Script + Manifest（エージェント: `immersive-scriptwriter`）
   - 入力: `story.md` + `visual_value.md`（必要なら `research.md` も参照）
   - 出力: `script.md` と `video_manifest.md`
7) `--stage video` のときのみ、素材生成→結合を実行して `video.mp4` を完成させる
   - `scripts/toc-immersive-ride-generate.sh --run-dir output/<topic>_<timestamp>`
8) `state.txt` に最終状態（`runtime.stage=done` と成果物パス）を追記する
   - `runtime.render.status=started|success|failed`
   - `artifact.video=output/<topic>_<timestamp>/video.mp4`
   - `review.video.status=pending`（人間が最終判定で `approved` を付ける）

人間の承認（例）:

```bash
python scripts/toc-state.py approve-video --run-dir output/<topic>_<timestamp> --note "OK"
```

## 実装ヘルパ（ローカルスクリプト）

台本/マニフェスト確定後の「生成→結合」一括実行:

```bash
scripts/toc-immersive-ride-generate.sh --run-dir output/<topic>_<timestamp>
```

メモ:
- 生成のシームレス性を上げるため、`last_frame` 制約 + chaining（前動画終盤フレームを次の first frame に使用）+ ネガティブプロンプトを併用する
- 音声（ナレーション）はデフォルト必須。意図的にサイレントで進める場合は `scripts/generate-assets-from-manifest.py --skip-audio` を使う（その場合はサイレント動画として書き出す）
- ただし `visual_value.md` に基づく silent cut は例外で、`audio.narration.tool: "silent"` と `text: ""` を使って部分的に無音へできる
- 後から中間scene（例: 35）を差し込めるように、`scene_id` は **10刻み**（例: 10,20,30...）を推奨（後段はmanifest順を正とする）
- コスト/反復のため、画像は `--image-batch-size 10 --image-batch-index 1` のように **10枚ずつ**生成して進められる

## 重要な原則（プロンプト要件）

### DO

- 全プロンプトに必ず入れる（invariants）:
  - `視点（POV/三人称）`（必要なら明示し、1カット内でブレない）
  - `No on-screen text`（映像だけで伝える）
- 参照画像を全生成に含める（キャラクター・重要小道具。手元/乗り物アンカーは前提にしない）
- scene間の連続性（照明・雰囲気・位置関係の自然な遷移）
- `cloud_island_walk`: 道/橋/階段など「前進の導線」を常に画面内に置く（歩み＝理解の進行）

キャラクター参照（turnaround）:
- `assets/characters/<id>.png`（または `<id>_front.png`）を1枚用意し、
  `scripts/toc-immersive-ride-generate.sh`（内部で `--character-reference-views front,side,back --character-reference-strip`）で
  `*_side.png` / `*_back.png` / `*_refstrip.png` を自動生成して動画側の参照に使う。

### DON'T

- `animated / animation / cartoon / anime / illustrated / drawing`
- `Studio Ghibli style`
- 視点のブレ（同一カット内でカメラ位置/高さが不自然に変わる）
- `cloud_island_walk` での禁止: `third-person / over-the-shoulder / selfie`（外側カメラへの切替）

## 参照

- 仕様（正本）: `docs/implementation/immersive-ride-entrypoint.md`
- 動画生成の契約: `docs/implementation/video-integration.md`
- 実行全体: `docs/how-to-run.md`
