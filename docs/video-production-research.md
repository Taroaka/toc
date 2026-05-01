# Video Production Research (Providers & Gaps)

本ドキュメントは、`output/momotaro_20260110_1700/` を **実際に画像/動画生成APIで素材化**する前段として、
現状の設計ドキュメントを棚卸しし、**「まだ揃っていないもの」を調査項目として明確化**するためのメモ。

## 目的

- 画像生成/動画生成の **主要API候補**を把握する（有名どころ＋API提供の有無）
- 生成AIで動画制作をするために必要な要素を洗い出し、**不足分を調査リスト**に落とす
- 抽象→具体の両面で「ある/ない」を 2x2 マトリックスで整理し、次の実装タスクへ繋ぐ

## 現状（すでにあるもの）

- 物語/台本/マニフェストのスキーマと作り方: `docs/story-creation.md`, `docs/script-creation.md`, `docs/video-generation.md`
- Director（監督）エージェント定義: `.claude/agents/director.md`
- 動画マニフェストテンプレ: `workflow/video-manifest-template.md`
- 合成（結合）系の補助: `scripts/build-clip-lists.py`, `scripts/render-video.sh`
- 未決定事項の集約: `docs/open-decisions.md`（Providers / subtitles / BGM/SFX 等）

## 参考: 最近の「生成AIで動画制作」パターン（ユーザー要約の反映）

動画制作を生成AIで回す際の、現実的な分割（役割）と、特に重要な観点（データ/評価）を整理する。

### 採用スタック（決定）

- 画像: Google Nano Banana 2（`google_nanobanana_2`）
- 画像（代替）: Gemini 3.1 Flash Image（`gemini_3_1_flash_image` / `gemini-3.1-flash-image-preview`）
- 動画: Google Veo 3.1（`veo-3.1-generate-preview`）
- 音声（TTS）: ElevenLabs

### ざっくりの工程

1. 企画（トピック）: 人間が決める
2. 調査→物語設計: AIが調査後、`docs/story-creation.md` に沿って `story.md` を作る
3. シーン分割→サブエージェント: sceneごとに「画像の設定を持ったプロンプト」を作る
4. 音声（TTS）: `ElevenLabs`（voice/model/output_format を運用で確定）

### 生成で一番大事: 「データ」と「評価」

- データ（dataset）: 「入力例」と「理想の出力」のペア
  - 例（このリポジトリ文脈）:
    - 入力: `script.md` の scene（構造化された scene spec）
    - 理想: 画像プロンプト / 動画モーションプロンプト / テロップ指示 / 期待アセット構成
- 評価基準（criteria）: 「生成結果がどうだったら良いとみなすか」
- 目標（ゴール）を先に定義し、AIに複数案を出させ、評価でスコアリングして最良を採用する
  - 改善が必要なら、差分分析→プロンプト改善の反復を行う

### Prompt Optimizer（概念: 構造だけを採用）

※ 別領域（スライド生成）の例から「構造」を参考にする。具体的な重み/項目のコピーはしない。

- 入力:
  - `prompt`（scene→image/video などの生成指示を作るためのテンプレ/方針）
  - `workflow/datasets/`（入力と理想出力のペア）
  - `workflow/evaluation_criteria.md`（採点軸）
- ループ（最小）:
  1. dataset をサンプリングして評価（過適合を避ける）
  2. 現状promptで出力を生成
  3. 理想との差分を分析
  4. 基準に沿ってスコア化
  5. prompt を改善
  6. 収束条件（回数上限 or スコア閾値）で停止
- ログ:
  - 各イテレーションで「選んだdataset」「スコア」「問題点」「改善内容」を記録する

## 2x2 マトリックス（抽象/具体 × ある/ない）

| | **具体: ある** | **具体: ない** |
|---|---|---|
| **抽象: ある** | **(A) 安定領域**  | **(B) 具体化待ち** |
| **抽象: ない** | **(C) 暗黙の実装** | **(D) 未定義/未整備** |

### (A) 抽象:ある × 具体:ある（安定領域）

- Story / Script / Video manifest のスキーマと作成ガイド
- 合成（FFmpeg）周りのユーティリティ（結合リスト生成、レンダリングスクリプト）
- state を `state.txt`（追記型）で管理する方針（再開/擬似ロールバック）

### (B) 抽象:ある × 具体:ない（具体化待ち）

- プロバイダの **運用仕様の詰め**（採用は済み。API制約/パラメータ/エラー/保存形式/メタデータを確定）
- **プロバイダ差分を吸収するアダプタI/F**（エラー/リトライ/保存形式/メタデータの標準化）
- **生成プロンプトの正本**（テンプレ、固定プロンプト、参照画像の使い方、ネガティブ等の標準）
- **Prompt Optimizer**（dataset + 評価基準 + 反復改善）をどの粒度で回すか
- **キャラクター一貫性**の運用（character bible をどう作り、どのAPI機能で担保するか）
- **品質ゲート**（OK/NG判定は定義済みだが、判定手法・自動化範囲が未確定）

### (C) 抽象:ない × 具体:ある（暗黙の実装）

- 既存のスクリプト群が前提にしている「入力ファイルの置き方/命名/手順」が、正本としてはまだ薄い
  - 例: `scripts/build-clip-lists.py` が期待する manifest の `output:` フィールド運用

### (D) 抽象:ない × 具体:ない（未定義/未整備）

- 字幕（SRT）生成の方式（script→SRT、TTS音声と同期、フォント/焼き込み）
- BGM/SFX の扱い（生成/内製/なし、ミキシング基準）
- 生成コスト/レート制限/同時実行・失敗時の再実行ポリシー（最小でも運用ルールは必要）
- prompt の評価データ（dataset）をどこに、どんな形式で、どう更新するか（運用）

## 主要プロバイダ候補（画像/動画）

下記は「有名で、APIとして扱える（または扱える可能性が高い）」ものを中心に列挙。
最終採用は別途（コスト/品質/制御性/日本語/商用条件）で決める。

### 画像生成（API）

- OpenAI Images API（生成/編集/バリエーション）: https://platform.openai.com/docs/guides/image-generation
- Google Vertex AI（Imagen）: https://cloud.google.com/vertex-ai/generative-ai/docs/imagen/overview
- Adobe Firefly Services（Generate Image など）: https://developer.adobe.com/firefly-services/docs/firefly-api/guides/
- Stability AI（Image/SD系）: https://stabilityai.apidog.io/

### 動画生成（API）

- OpenAI Video generation（Sora）: https://platform.openai.com/docs/guides/video
- Google Vertex AI（Veo）: https://cloud.google.com/vertex-ai/generative-ai/docs/video/overview
- Runway API（image-to-video / text-to-video）: https://docs.dev.runwayml.com/
- Luma API（Dream Machine / Ray 系）: https://docs.lumalabs.ai/docs
- Pika（APIプログラム/パートナー提供の可能性）: https://early-access.pika.art/api/
- Stability AI（Stable Video Diffusion）: https://stability.ai/news/stable-video-diffusion-api

### “統合API”/マーケットプレイス（複数モデルを一つのAPIで）

- Replicate（多様なモデルをAPIで実行）: https://replicate.com/docs
- fal.ai（多様なモデルをAPIで実行）: https://fal.ai/docs

### 注意（人気だがAPIが弱い/非公式になりがち）

- Midjourney は公式APIが限定的/Discord中心のため、パイプライン自動化の中核には置きづらい

## 調査リスト（不足分を埋める）

### 1) プロバイダ選定（画像/動画）

採用プロバイダ（Nano Banana 2 / Gemini 3.1 Flash Image / Veo 3.1 / ElevenLabs）について、運用に必要な仕様を詰める。

- 画像（Nano Banana 2 / Gemini 3.1 Flash Image）:
  - 入出力仕様（解像度、アスペクト比、参照画像、ネガティブ）
  - 生成結果の安定性（同一プロンプト/seedでの再現性）
  - 料金体系とレート制限（バッチ可否、同時実行）
- 動画（Veo 3.1）:
  - image-to-video（first frame / reference images）の使い方と制約
  - `durationSeconds`/`aspectRatio`/`resolution` の制約と scene 分割戦略
  - 失敗時のリトライ設計（LRO、ポーリング、タイムアウト）

**成果物（調査のアウトプット）**
- `docs/open-decisions.md` の Providers を「採用 + 運用仕様」まで具体化
- `workflow/video-manifest-template.md` の `tool:` 値を採用名に合わせる

### 2) 生成プロンプトの正本化（プロバイダ差分を吸収）

- “台本→生成”の最小契約を固定する（sceneごとに最低何が必要か）
  - 画像: subject/style/environment/lighting/camera + ネガティブ + 参照（任意）
  - 動画: base_image + motion_prompt（カメラ/動き） + 参照（任意）
- 参照画像（character/style）をどう管理し、どのAPI機能に渡すかを調査
- “固定プロンプト”をどこに置くか（`script.md` / `video_manifest.md` / `assets/character_bible.*`）
- dataset / 評価基準を用意して prompt を反復改善できるようにする（Prompt Optimizer）

**成果物**
- `workflow/video-manifest-template.md` に「必須/任意」フィールドを明記（雛形を確定）
- Providerごとの prompt mapping（最小）を 1ページにまとめる（後で実装に使う）
- `workflow/evaluation_criteria.md` と `workflow/datasets/`（入力と理想出力のペア）の置き場所/形式を決める

### 3) 字幕（SRT）とテロップ

- 字幕の生成源を決める（scriptの narration/dialogue を直接SRT化 で良いか）
- 同期の考え方（等間隔配分 / 文字数ベース / TTS音声の実測）
- 焼き込み方式（FFmpeg / Remotion 等）と日本語フォント

**成果物**
- `docs/open-decisions.md` の Rendering details を具体化

### 4) 音声（TTS）と BGM/SFX（必要なら）

- TTS: ElevenLabs の voice/model/output_format を運用で確定する（日本語品質/速度/コスト）
- BGM/SFX: MVPでは「なし」or「固定テンプレ」or「生成」を選択（設計だけ先に決める）

**成果物**
- `workflow/video-manifest-template.md` の audio セクション運用を確定（最低限 narration）

### 5) 運用（失敗時の再実行・保存・キャッシュ）

- 生成APIの非同期ジョブの取り扱い（job_id を state に残す/再開する）
- “原本”として保存すべきもの（プロンプト、seed、モデル名、レスポンスJSON、参照画像）
- キャッシュ方針（テキスト/JSONは保存、画像/動画はそのままストレージ）

**成果物**
- state へ記録するキー（例: `image_provider`, `video_provider`, `job_id`, `seed`, `model`）を決める
