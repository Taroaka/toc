# Orchestration / QA / Compliance / Publishing

運用設計ドキュメント（追加レイヤー）

## 位置づけ

```
[情報収集] → [物語生成] → [動画生成] → [配信/分析] → [改善]
         ↑           ↑           ↑           ↑           ↑
         docs/information-gathering.md
                     docs/story-creation.md
                                 docs/video-generation.md
                                                    本書
```

本書は、上記3システムを**一連の組織プロセス**として統合し、品質・権利・運用・改善の仕組みを定義する。

---

## 1. Orchestration（全体制御）

### 1.1 目的
- サブエージェントの順序・依存関係・再実行を管理する
- 人間の承認ゲートを明示する
- すべての成果物をトレース可能にする

### 1.2 ステートマシン

```
INIT → RESEARCH → STORY → VIDEO → PUBLISH → ANALYZE → IMPROVE → DONE
        ↑   └─────────────┐
        └── RETRY/REVISE ─┘
```

### 1.3 オーケストレーション・マニフェスト

```yaml
job:
  job_id: "JOB_2026-01-10_0001"
  topic: "桃太郎"
  created_at: "ISO8601"
  status: "RESEARCH | STORY | VIDEO | PUBLISH | ANALYZE | IMPROVE | DONE"

inputs:
  user_prompt: "string"
  constraints:
    duration_seconds: 60
    aspect_ratio: "9:16"
    language: "ja"

artifacts:
  research: "output/<topic>_<timestamp>/research.md"
  story: "output/<topic>_<timestamp>/story.md"
  video: "output/<topic>_<timestamp>/video.mp4"
  improvement: "output/<topic>_<timestamp>/improvement.md"

gates:
  research_review: "required | optional | skipped"
  story_review: "required | optional | skipped"
  video_review: "required | optional | skipped"

audit:
  steps:
    - step: "RESEARCH"
      status: "done"
      reviewer: "human | auto"
      notes: "string"
```

### 1.4 実行ルール
- **必須レビューゲート**: 事実性（Research）と最終納品（Video）
- **自動再試行**: 失敗原因が機械的（APIエラー、品質低下）の場合のみ
- **人間レビュー**: 重要テーマ（時事、政治、医療、法律）は強制

### 1.4.1 canonical state の書き分け

`state.txt` では、`status=` と `stage.*.status=` を分けて扱う。

- `status=`
  - 粗い現在地
- `stage.*.status=`
  - 作業単位の完了状況
  - `awaiting_approval` は、作業は終わったが承認待ちで停止している状態

標準 stage:

- `stage.research`
- `stage.story`
- `stage.visual_value`
- `stage.script`
- `stage.image_prompt_review`
- `stage.image_generation`
- `stage.video_generation`
- `stage.narration`
- `stage.render`
- `stage.qa`

各作業は **開始時** と **完了時** に append する:

1. 開始時:
   - `stage.<name>.status=in_progress`
   - `stage.<name>.started_at=...`
2. 完了時:
   - 承認不要なら `stage.<name>.status=done`
   - 承認待ちが必要なら `stage.<name>.status=awaiting_approval`
   - `stage.<name>.finished_at=...`
3. 失敗時:
   - `stage.<name>.status=failed`
   - `last_error=...`

標準で承認待ちを挟む stage:

- `stage.script`
- `stage.image_generation`
- `stage.narration`

この 3 つが `awaiting_approval` の間は、**次工程へ進まない**。

承認待ちの stage を報告するときは、単に `awaiting_approval` と書くだけで終わらせず、次にユーザーがレビューすべき対象を短く明示して確認を促す。

対応 review:

- `review.script.status`
- `review.image.status`
- `review.narration.status`

これにより、`state.txt` だけで

- 調査は終わった
- 物語は終わった
- ナレーションは終わった
- render はまだ

のような読み方ができる。

### 1.5 VIDEOステージの内部サブフロー

```
VIDEO:
  1) シーン静止画生成・選定
  2) Image-to-Video クリップ生成
  3) ナレーション/BGM/SFX 生成
  4) クリップ結合 + 音声ミックス
  5) 字幕作成・焼き込み
  6) 最終レンダリング（mp4出力）
  7) 品質ゲート通過
```

### 1.6 mp4出力の必須条件

```yaml
video_delivery_gate:
  mp4_exists: true
  duration_ok: true
  audio_sync: true
  subtitle_ok: true
  aspect_ratio_ok: true
```

---

## 2. QA（品質評価）

### 2.1 目的
- 事実の正確性、物語の一貫性、視聴体験の質を保証
- 再現性のある評価指標を提供

### 2.2 QAチェックリスト

```yaml
qa_checks:
  factual_accuracy:
    min_confidence: 0.7
    verified_facts_ratio: 0.8
    no_fabrication: true

  narrative_quality:
    hook_strength: "good | fair | weak"
    tension_curve: "clear | uneven | flat"
    transformation_present: true

  visual_consistency:
    character_consistency: true
    style_consistency: true

  audio_quality:
    narration_clarity: true
    bgm_balance: true
    sfx_timing: true
```

### 2.3 評価スコア（例）

```yaml
qa_scores:
  accuracy_score: 0.0-1.0
  engagement_score: 0.0-1.0
  consistency_score: 0.0-1.0
  overall_score: 0.0-1.0
  pass_threshold: 0.75
```

### 2.4 フェイル時の対応
- `accuracy_score < 0.75` → Researchを再実行
- `engagement_score < 0.7` → Storyを再実行
- `consistency_score < 0.7` → Videoを再実行

---

## 3. Compliance（権利・倫理・安全）

### 3.1 目的
- 著作権侵害・肖像権・人格権リスクを抑える
- AI利用の透明性を確保する

### 3.2 ルールセット

```yaml
compliance_rules:
  copyright:
    prohibit_direct_copy: true
    require_source_tracking: true
  likeness:
    real_person: "consent_required"
    public_figure: "caution_required"
  data_usage:
    training_opt_out: "respect"
    api_terms: "enforced"
  disclosure:
    ai_generated_notice: true
```

---

## 4. Publishing（配信・分析・改善ループ）

### 4.1 配信設計
- チャンネルの戦略（Shorts/Long/Series）
- タイトル/サムネ/説明文のテンプレ

### 4.2 分析指標

```yaml
analytics:
  retention:
    average_view_duration: "seconds"
    relative_retention: "above | average | below"
  engagement:
    like_ratio: 0.0-1.0
    comment_rate: 0.0-1.0
    share_rate: 0.0-1.0
  growth:
    subscribers_delta: int
```

### 4.3 改善エージェント（4番目）

```yaml
improvement_agent:
  inputs:
    - "output/<topic>_<timestamp>/video.mp4"
    - "analytics_metrics.json"
    - "comment_samples.json"
  outputs:
    - "output/<topic>_<timestamp>/improvement.md"
  tasks:
    - "競合比較（構成/テンポ/フック）"
    - "改善仮説の提示"
    - "次回A/Bテスト案の提案"
```

---

## 5. ディレクトリ構成（推奨）

```
output/
  <topic>_<timestamp>/
    research.md
    story.md
    video_manifest.md
    video.mp4
    improvement.md
    clips.txt
    narration_list.txt
    assets/
      characters/
      styles/
      scenes/
      audio/
logs/
  orchestration/
```

---

## 6. 連携ポイント

- **Research → Story**: 事実性とフックの転写
- **Story → Video**: シーン分解とスタイルガイドの適用
- **Video → Publishing**: タイトル/サムネ/説明の生成
- **Publishing → Improvement**: 視聴維持とコメント分析を反映

---

## 7. 最小実装（MVP）手順

```
1. Research実行 → 出力生成
2. Story実行 → 台本生成
3. Video実行 → mp4生成
~まずはここまで
4. 手動でYouTube公開
5. 1週間後、コメントと維持率を収集
6. Improvement実行 → 改善案を次作に反映

```

---

## 8. 1物語フォルダ作成（補助）

```bash
scripts/create-story-folder.py --topic momotaro
# 例: output/momotaro_20260111_0930/ が生成される
```
