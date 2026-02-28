# /toc-immersive-ride

ToC（TikTok Story Creator）で「没入型（First-person POV）実写シネマ・ライド体験」動画を単発で生成するコマンド。

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

- First-person POV（一人称視点）
- 実写風シネマティック（photorealistic / cinematic / practical effects）
- ガイドは **音声（ナレーション）として必須**（視覚的に登場させない）

`ride_action_boat`（legacy / optional）:

- テーマパークの “ride action boat” でトピック世界を巡る
- 統一要素:
  - 人間の手（年齢/性別は指定しない。必要なら作品側で指定）
  - ornate brass safety bar
  - 乗り物（線路/ガイドに沿って進む）
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
- `research.md`
- `story.md`
- `script.md`
- `video_manifest.md`
- `assets/**`
- `video.mp4`（完成動画。1280x720 / 24fps）

## 実行フロー（内部の意図）

```text
topic
  → Deep Research（deep-researcher）
  → Story（director）
  → Script + Manifest（immersive-scriptwriter）
  → Generate assets（API）
  → Render final video（ffmpeg）
```

## 引数

$ARGUMENTS:
- `--topic "<topic>"` (required)
- `--stage video|script` (optional, default: `video`)
  - `video`: 完成動画まで生成する（API + ffmpeg を含む）
  - `script`: `research.md` / `story.md` / `script.md` / `video_manifest.md` まで作って止める
- `--experience ride_action_boat|cloud_island_walk` (optional, default: `cloud_island_walk`)
  - `ride_action_boat`: 従来のテーマパーク・ライド（ボート/安全バー）パターン
  - `cloud_island_walk`: 雲上の島を歩いて理解を深める（哲学/概念の比喩）パターン
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
5) Script + Manifest（エージェント: `immersive-scriptwriter`）
   - 入力: `story.md`（必要なら `research.md` も参照）
   - 出力: `script.md` と `video_manifest.md`
6) `--stage video` のときのみ、素材生成→結合を実行して `video.mp4` を完成させる
   - `scripts/toc-immersive-ride-generate.sh --run-dir output/<topic>_<timestamp>`
7) `state.txt` に最終状態（`runtime.stage=done` と成果物パス）を追記する
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
- 音声が無い場合はサイレント動画として書き出す
- 後から中間scene（例: 35）を差し込めるように、`scene_id` は **10刻み**（例: 10,20,30...）を推奨（後段はmanifest順を正とする）
- コスト/反復のため、画像は `--image-batch-size 10 --image-batch-index 1` のように **10枚ずつ**生成して進められる

## 重要な原則（プロンプト要件）

### DO

- 全プロンプトに必ず入れる（invariants）:
  - `First-person POV ...`（experience に合わせて明示する: `ride_action_boat`=boat/vehicle, `cloud_island_walk`=walking forward）
  - `No on-screen text`（映像だけで伝える）
  - `Realistic hands ...`（`ride_action_boat` では必須。`cloud_island_walk` は必須ではない）
- 参照画像を全生成に含める（キャラクター・手元アンカー・必要なら乗り物/環境の参照）
- scene間の連続性（照明・雰囲気・位置関係の自然な遷移）
- `ride_action_boat`: 乗り物は必ず **アトラクションの線路/ガイド** に沿って進む（隠し方は driftwood 等でOK）
- `cloud_island_walk`: 道/橋/階段など「前進の導線」を常に画面内に置く（歩み＝理解の進行）

キャラクター参照（turnaround）:
- `assets/characters/<id>.png`（または `<id>_front.png`）を1枚用意し、
  `scripts/toc-immersive-ride-generate.sh`（内部で `--character-reference-views front,side,back --character-reference-strip`）で
  `*_side.png` / `*_back.png` / `*_refstrip.png` を自動生成して動画側の参照に使う。

### DON'T

- `animated / animation / cartoon / anime / illustrated / drawing`
- `Studio Ghibli style`
- 視点のブレ（前進の導線が消える、地平線が揺れる、カメラ高さが変わる）
- `cloud_island_walk` での禁止: `third-person / over-the-shoulder / selfie`（外側カメラへの切替）

## 参照

- 仕様（正本）: `docs/implementation/immersive-ride-entrypoint.md`
- 動画生成の契約: `docs/implementation/video-integration.md`
- 実行全体: `docs/how-to-run.md`
