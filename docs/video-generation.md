# Video Generation System

動画生成システム - 物語スクリプトから最終動画を生成する手順書

## 概要

このドキュメントは、`docs/story-creation.md` で生成した物語スクリプトを、生成AIを活用して動画に変換するための手順を定義する。

### 関連ドキュメント

- `docs/orchestration-and-ops.md`（全体制御・品質保証・配信/改善ループ）

### 位置づけ

```
[情報収集] → [物語生成] → [動画生成]
                           ↑ 本書
```

### 入力

- `output/<topic>_<timestamp>/story.md` - 物語スクリプト
- シーンごとの視覚・音声指示

### 出力

- `output/<topic>_<timestamp>/video.mp4` - 最終動画ファイル

---

## 第1章：原則と哲学（抽象レイヤー）

### 1.1 生成AIを動画制作に使う根本的考え方

#### AIは「ツール」であり「クリエイター」ではない

生成AIは人間の創造性を**増幅**するツールであり、**置換**するものではない。

```
[人間の役割]                    [AIの役割]
・ビジョンと意図の設定          ・大量の素材生成
・品質の最終判断                ・反復的な作業の自動化
・感情的真正性の担保            ・技術的制約の克服
・倫理的判断                    ・スピードとスケール
```

#### Netflix のガイドライン原則（参考）

- 生成物は著作権素材を複製しない
- ツールは制作データを保存・再利用・学習に使用しない
- 生成素材は一時的なものであり、最終成果物の一部としない場合もある
- タレントの演技や組合対象の作業を同意なく置き換えない

### 1.2 品質を担保するための設計思想

#### 「生成」より「選択」

```
[悪いアプローチ]
1回生成 → そのまま使用

[良いアプローチ]
複数回生成 → 比較 → 最良を選択 → 必要なら再生成
```

**原則**: 生成AIの出力はバラつきがある。品質は「生成の質」ではなく「選択の質」で決まる。

#### 生成静止画は「毎回」ではなく「必要なとき」に作る

- 新規の静止画生成は、同じ場所/物体/人物状態の continuity anchor を作るときに優先する
- すでに anchor frame や参照画像がある scene/cut は、それを再利用してよい
- 目的は「全scene/cutに1枚ずつ新規画像を作ること」ではなく、後続の cut で迷わない共通参照を確保すること

#### 段階的精緻化（Progressive Refinement）

```
[粗い設計] → [中間検証] → [詳細設計] → [最終検証]
    ↓             ↓            ↓            ↓
  コンセプト    ラフ動画      素材生成      最終合成
  承認          方向性確認    品質確認      出力
```

**原則**: 早期段階で方向性を確定し、後工程での手戻りを最小化する。

### 1.3 よくある失敗パターンと回避策

| 失敗パターン | 原因 | 回避策 |
|------------|------|--------|
| **一貫性の欠如** | シーンごとに異なるスタイル | キャラクターバイブル作成、参照画像の固定 |
| **不自然な動き** | 物理法則の無視 | モデル選択の最適化、手動補正の許容 |
| **品質のばらつき** | 1回生成で確定 | 複数生成→選択のワークフロー |
| **コスト超過** | 無計画な再生成 | 静止画での事前検証、バッチ処理 |
| **スタイル漂流** | プロンプトの曖昧さ | 固定フレーズの使用、LoRAトレーニング |

### 1.4 コスト・品質・速度のトレードオフ

```
        品質
         ↑
         │    ★ 理想
         │   /|\
         │  / | \
         │ /  |  \
         │/   |   \
    ────┼────┼────→ 速度
        /│   │
       / │   │
      /  │   │
     ↓   │   │
   コスト  │   │
```

**現実的な選択**:

| 優先事項 | 推奨アプローチ |
|---------|--------------|
| 品質優先 | 高品質モデル（Sora 2）、多数生成→厳選、手動補正許容 |
| 速度優先 | 軽量モデル（Pika）、シンプルなシーン、自動パイプライン |
| コスト優先 | オープンソース（SD）、ローカル実行、バッチ最適化 |

---

## 第2章：設計レイヤー

### 2.1 ワークフロー全体設計

```
┌─────────────────────────────────────────────────────────────┐
│                    動画生成パイプライン                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [物語スクリプト]                                           │
│       ↓                                                     │
│  [1. プリプロダクション]                                    │
│       ├→ キャラクターバイブル作成                          │
│       ├→ スタイルガイド定義                                │
│       └→ シーン分解                                        │
│       ↓                                                     │
│  [2. 素材生成]                                              │
│       ├→ 参照画像生成（Image Gen）                         │
│       ├→ 動画クリップ生成（Image-to-Video）                │
│       └→ 音声生成（TTS / Music）                           │
│       ↓                                                     │
│  [3. ポストプロダクション]                                  │
│       ├→ クリップ編集・トリミング                          │
│       ├→ トランジション追加                                │
│       ├→ 音声同期                                          │
│       └→ 字幕・テロップ追加                                │
│       ↓                                                     │
│  [4. 最終レンダリング]                                      │
│       └→ エンコード・出力                                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Image-to-Video ワークフロー

**原則**: 静止画での検証を先行させ、動画生成コストを最小化する。

```
[推奨ワークフロー]

Step 1: 静止画生成（低コスト）
        ├→ 複数バリエーション生成
        ├→ 最適な1枚を選択
        └→ 必要なら再生成

Step 2: 画像→動画変換（高コスト）
        ├→ 選択した静止画を入力
        ├→ モーション指示を追加
        └→ 動画クリップ生成

Step 3: 品質確認
        ├→ OK → 次のシーンへ
        └→ NG → Step 1 or 2 に戻る
```

**理由**: 動画生成は画像生成の10-100倍のコスト。静止画での事前検証が最も効率的。

### 2.3 一貫性を保つ手法

#### キャラクターバイブル（Character Bible）

```yaml
character_bible:
  name: "主人公A"
  visual_identity:
    face: "oval face, brown eyes, short black hair"
    body: "medium height, slim build"
    outfit: "blue denim jacket, white t-shirt, black jeans"
    accessories: "silver watch on left wrist"

  fixed_phrases:  # プロンプトで毎回使用
    - "oval face with brown eyes"
    - "short black hair"
    - "blue denim jacket over white t-shirt"
    - "silver watch on left wrist"

  reference_images:
    - path: "assets/character_a_front.png"
    - path: "assets/character_a_side.png"
```

**運用ルール**:
- 同じキャラクターには**同じフレーズを毎回使用**
- 「coat」と「jacket」など類似語の混在を避ける
- 参照画像を固定し、フレーム間でアンカーとして使用

#### スタイルガイド

```yaml
style_guide:
  visual_style: "cinematic, warm color grading, shallow depth of field"
  aspect_ratio: "16:9"  # or "9:16" for vertical
  lighting: "soft natural lighting, golden hour tone"

  forbidden:
    - "cartoon style"
    - "anime"
    - "watercolor"

  reference_images:
    - path: "assets/style_reference_1.png"
    - path: "assets/style_reference_2.png"
```

#### フレーム間チェーニング

```
[シーン1の最終フレーム] → [シーン2の参照画像として入力]
                              ↓
                        シームレスな接続
```

### 2.4 プロンプトエンジニアリング原則

#### 構造化プロンプトテンプレート

```
[主題] + [スタイル] + [環境] + [照明] + [カメラ] + [動き]

例:
"A young woman with oval face and short black hair,
wearing blue denim jacket,
standing in a modern coffee shop,
soft natural lighting from large windows,
medium shot,
slowly turning her head to the right"
```

#### プロンプト設計のDo/Don't

| Do | Don't |
|----|-------|
| 具体的な特徴を列挙 | 曖昧な形容詞（beautiful, nice） |
| 固定フレーズを繰り返す | 同義語で言い換える |
| 参照画像と組み合わせる | テキストのみに依存 |
| カメラワークを明示 | カメラを暗示に任せる |
| ネガティブプロンプト活用 | 禁止事項を書かない |

### 2.5 音声・BGM・効果音との同期設計

```
[タイムライン設計]

00:00 ─────────────────────────────────── 01:00
  │                                         │
  ├─ VIDEO ──────────────────────────────────┤
  │  Scene1   Scene2   Scene3   Scene4      │
  │                                         │
  ├─ NARRATION ──────────────────────────────┤
  │  "..."    "..."    "..."    "..."       │
  │                                         │
  ├─ BGM ────────────────────────────────────┤
  │  ♪ intro  ♪ build  ♪ climax ♪ resolve  │
  │                                         │
  └─ SFX ────────────────────────────────────┤
     *ding*         *whoosh*    *impact*    │
```

**同期ポイント**:
- シーン切り替えと音楽の変化を合わせる
- 感情のピークでBGMも盛り上げる
- 重要な瞬間に効果音を配置

---

## 第3章：技術選定レイヤー

### 3.1 画像生成AI比較

| ツール | 強み | 弱み | 最適用途 |
|--------|------|------|----------|
| **DALL-E 3** | プロンプト理解力、安全性 | スタイル制御が限定的 | 概念実証、一般用途 |
| **Midjourney** | 芸術性、美的品質 | API未提供（Discord経由） | アート志向、スタイル重視 |
| **Stable Diffusion** | カスタマイズ性、ローカル実行 | セットアップの複雑さ | 大量生成、カスタムモデル |
| **Leonardo.ai** | キャラクター参照機能 | 無料枠の制限 | キャラクター一貫性 |
| **Flux** | 高品質、一貫性機能 | 新興サービス | バランス型 |

### 3.2 動画生成AI比較

| ツール | 強み | 弱み | 最適用途 |
|--------|------|------|----------|
| **Sora 2** | 最高の映像品質、音声同時生成 | 高コスト、アクセス制限 | プレミアムコンテンツ |
| **Runway Gen-4** | 精密な制御、プロ向けツール群 | 学習曲線が急 | プロフェッショナル制作 |
| **Pika Labs** | 使いやすさ、コスパ | 長尺動画に弱い | 初心者、SNS向け |
| **Kling** | キャラクター一貫性、2D/3Dバランス | 日本語対応不十分 | アニメスタイル |
| **Luma Dream Machine** | 高速生成 | 品質の安定性 | プロトタイピング |
| **Veo 3** | リアリズム | Google限定エコシステム | 実写風コンテンツ |

### 3.3 Image-to-Video vs Text-to-Video

```
[Image-to-Video] ★推奨
入力: 静止画 + モーション指示
利点: 一貫性が高い、コスト効率が良い
欠点: 事前に画像生成が必要

[Text-to-Video]
入力: テキストプロンプトのみ
利点: ワンステップで生成可能
欠点: 一貫性の制御が困難、コスト高
```

**推奨**: Image-to-Videoを基本とし、静止画での事前検証を徹底する。

### 3.4 音声生成AI比較

| ツール | 強み | 用途 |
|--------|------|------|
| **ElevenLabs** | 自然な音声、感情表現 | ナレーション、キャラクター音声 |
| **OpenAI TTS** | 安定性、多言語 | 汎用ナレーション |
| **Google TTS** | 低コスト、多言語 | 大量生成 |
| **Suno** | 音楽生成 | BGM |
| **Udio** | 音楽生成、スタイル制御 | BGM |

---

## 第4章：実装レイヤー

### 4.1 推奨ツールチェーン

```
[静止画生成]     [動画生成]      [音声生成]     [合成]
Midjourney  →   Runway      +   ElevenLabs  →  FFmpeg
    or              or              or           or
Stable Diffusion   Pika         OpenAI TTS    MoviePy
    or              or
DALL-E 3         Kling
```

### 4.2 FFmpeg基本操作

#### 画像から動画を生成

```bash
# 静止画を5秒の動画に変換
ffmpeg -loop 1 -i image.png -c:v libx264 -t 5 -pix_fmt yuv420p output.mp4

# 連番画像から動画を生成
ffmpeg -framerate 24 -i frame_%04d.png -c:v libx264 -pix_fmt yuv420p output.mp4
```

#### 動画の結合

```bash
# ファイルリストから結合
ffmpeg -f concat -safe 0 -i filelist.txt -c copy output.mp4

# filelist.txt の内容:
# file 'clip1.mp4'
# file 'clip2.mp4'
# file 'clip3.mp4'
```

#### 音声の追加

```bash
# 動画に音声を追加
ffmpeg -i video.mp4 -i audio.mp3 -c:v copy -c:a aac -shortest output.mp4

# BGMを追加（音量調整付き）
ffmpeg -i video.mp4 -i bgm.mp3 -filter_complex "[1:a]volume=0.3[bgm];[0:a][bgm]amix=inputs=2" output.mp4
```

### 4.3 字幕・テロップの追加

#### SRT形式の字幕

```srt
1
00:00:00,000 --> 00:00:03,000
最初の字幕テキスト

2
00:00:03,500 --> 00:00:07,000
次の字幕テキスト
```

#### FFmpegで字幕を焼き付け

```bash
ffmpeg -i video.mp4 -vf "subtitles=subtitle.srt:force_style='FontSize=24,PrimaryColour=&HFFFFFF'" output.mp4
```

### 4.4 最終レンダリング設定

#### SNS向け推奨設定

```bash
# 縦型動画（9:16）- 高品質
ffmpeg -i input.mp4 \
  -vf "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -preset slow -crf 18 \
  -c:a aac -b:a 192k \
  output_vertical.mp4

# 横型動画（16:9）- 高品質
ffmpeg -i input.mp4 \
  -vf "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2" \
  -c:v libx264 -preset slow -crf 18 \
  -c:a aac -b:a 192k \
  output_horizontal.mp4
```

---

## 実行フロー

```
1. 物語スクリプト読み込み
   └→ output/<topic>_<timestamp>/story.md

2. プリプロダクション
   ├→ キャラクターバイブル作成
   ├→ スタイルガイド定義
   └→ シーン分解・タイムライン設計

3. 素材生成
   ├→ 参照画像生成（シーンごと）
   ├→ Image-to-Video変換
   └→ 音声生成（ナレーション、BGM、SFX）

4. ポストプロダクション
   ├→ クリップ編集
   ├→ トランジション追加
   ├→ 音声同期
   └→ 字幕追加

5. 最終レンダリング
   └→ output/<topic>_<timestamp>/video.mp4
```

---

## mp4作成の具体手順（実務フロー）

### 必要入力
- `output/<topic>_<timestamp>/story.md`（物語スクリプト）
- シーン分解テーブル（シーンID、尺、視覚/音声指示）
- 参照画像（各シーン）
- ナレーション音声（各シーン）
- BGM / SFX

### 生成・合成ステップ

```
Step A: シーン静止画の生成・選定
  - 各シーンで複数生成 → 1枚選定

Step B: Image-to-Video クリップ生成
  - シーン単位で動画クリップ化

Step C: ナレーション生成
  - 各シーンの台詞をTTS化

Step D: BGM/SFX 準備
  - 全体尺に合わせたBGM配置
  - 重要ポイントにSFX配置

Step E: クリップ結合と音声合成
  - クリップ結合 → 1本の動画
  - ナレーション + BGM + SFX をミックス

Step F: 字幕作成・焼き込み
  - SRT作成 → mp4へ焼き込み

Step G: 最終レンダリング
  - 解像度/アスペクト比/音量調整
  - output/<topic>_<timestamp>/video.mp4 出力
```

### 最低限の品質ゲート

```yaml
video_gate:
  clip_coverage: true            # 全シーンが動画化されている
  audio_sync: true               # ナレーションと映像が一致
  subtitle_readable: true        # 字幕が視認可能
  aspect_ratio_correct: true     # 9:16 or 16:9
  render_success: true           # mp4が生成される
```

---

## 出力スキーマ

```yaml
# === メタ情報 ===
video_metadata:
  topic: "string"
  source_story: "output/<topic>_<timestamp>/story.md"
  created_at: "ISO8601"
  duration_seconds: 60
  aspect_ratio: "16:9 | 9:16"
  resolution: "1920x1080 | 1080x1920"

# === 素材管理 ===
assets:
  character_bible:
    - character_id: "protagonist"
      reference_images:
        - "assets/characters/protagonist_front.png"
        - "assets/characters/protagonist_side.png"
      fixed_prompts:
        - "oval face with brown eyes"
        - "short black hair"

  style_guide:
    visual_style: "cinematic, warm tones"
    reference_images:
      - "assets/style/reference_1.png"

# === シーン別素材 ===
scenes:
  - scene_id: 1
    timestamp: "00:00-00:10"

    image_generation:
      tool: "midjourney | dalle3 | stable_diffusion"
      prompt: "string"
      output: "assets/scenes/scene1_base.png"
      iterations: 5
      selected: 3

    video_generation:
      tool: "runway | pika | kling"
      input_image: "assets/scenes/scene1_base.png"
      motion_prompt: "camera slowly zooms in"
      output: "assets/scenes/scene1_video.mp4"

    audio:
      narration:
        text: "string"
        tool: "elevenlabs | openai_tts"
        output: "assets/audio/scene1_narration.mp3"
      bgm:
        source: "assets/audio/bgm_intro.mp3"
        volume: 0.3
      sfx:
        - timestamp: "00:03"
          file: "assets/audio/sfx_whoosh.mp3"

# === 最終出力 ===
final_output:
  video_file: "output/<topic>_<timestamp>/video.mp4"
  thumbnail: "output/<topic>_<timestamp>/thumb.png"

# === 品質チェック ===
quality_check:
  visual_consistency: true
  audio_sync: true
  subtitle_readable: true
  aspect_ratio_correct: true
```

---

## 参考文献

### ガイド・概要

- [GarageFarm - AI Video Generators Complete Guide](https://garagefarm.net/blog/the-complete-guide-to-ai-video-generators)
- [Lovart - Best AI Video Generators Review](https://www.lovart.ai/blog/video-generators-review)
- [LetsEnhance - Best AI Video Generators Tested](https://letsenhance.io/blog/all/best-ai-video-generators/)
- [SkyWork - Sora 2 vs Veo 3 vs Runway Comparison](https://skywork.ai/blog/sora-2-vs-veo-3-vs-runway-gen-3-2025-ai-video-generator-comparison/)

### 一貫性・プロンプトエンジニアリング

- [Medium - How to Design Consistent AI Characters](https://medium.com/design-bootcamp/how-to-design-consistent-ai-characters-with-prompts-diffusion-reference-control-2025-a1bf1757655d)
- [Artlist - Consistent Character AI Pro Tips](https://artlist.io/blog/consistent-character-ai/)
- [Leonardo.ai - Character Consistency](https://leonardo.ai/news/character-consistency-with-leonardo-character-reference-6-examples/)

### 業界ガイドライン

- [Netflix - Using Generative AI in Content Production](https://partnerhelp.netflixstudios.com/hc/en-us/articles/43393929218323-Using-Generative-AI-in-Content-Production)

---

## 補助スクリプト

### クリップ/ナレーション一覧の生成

マニフェストから ffmpeg 用の `clips.txt` と `narration_list.txt` を生成する。

```bash
# 1本分
scripts/build-clip-lists.py \
  --manifest output/<topic>_<timestamp>/video_manifest.md

# 1物語フォルダ（manifest指定不要）
scripts/build-clip-lists.py \
  --story-dir output/<topic>_<timestamp>

# ディレクトリ一括
scripts/build-clip-lists.py \
  --dir output \
  --pattern "*_manifest.md"
```
