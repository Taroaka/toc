# Story Creation System

物語生成システム - Deep Researchの成果を動画向けの物語に加工する手順書

## 概要

このドキュメントは、`docs/information-gathering.md` で収集した構造化情報を、動画コンテンツの物語に変換するための手順を定義する。

### 関連ドキュメント

- `docs/orchestration-and-ops.md`（全体制御・品質保証・配信/改善ループ）
- `docs/video-generation.md`（下流の汎用動画生成原則）
- `workflow/playbooks/video-generation/kling.md`（`kling_3_0` / `kling_3_0_omni` を使う場合の provider 固有 prompt guide）

### 位置づけ

```
[情報収集] → [物語生成] → [視覚価値設計] → [台本作成] → [動画生成]
              ↑ 本書
```

### 入力

- `output/<topic>_<timestamp>/research.md` - Deep Researchの出力ファイル
- 構造化YAML形式の知識ベース

### 出力

- `output/<topic>_<timestamp>/story.md` - 物語スクリプト
- `output/<topic>_<timestamp>/visual_value.md` - 視覚化価値パートの設計メモ（後続エージェントが作成）
- 動画用台本（任意の長さに対応）

### 下流 prompt 設計への受け渡し

- Story は下流の `script.md` / `video_manifest.md` が **1 clip = 1意図** で分解しやすい粒度で設計する
- 動画プロバイダが未指定なら、汎用ルールとして `docs/video-generation.md` を前提にしてよい
- 動画プロバイダが `kling_3_0` / `kling_3_0_omni` と明示されている場合、後続 agent が参照する動画 prompt guide は
  `docs/video-generation.md` に加えて `workflow/playbooks/video-generation/kling.md` を優先する前提で、scene の意図を切り出す

---

## 創造と選択（重要）

物語価値の中心は、登場人物と物語世界（世界観）が生む **多様性**にある。
台本は「既に流行しているナラティブを映像化する」ことが多いため、素材は高得点になりやすい。

そのため本プロジェクトでは、次を優先する:

- **創造（Creation）**: 解釈/視点/キャラクター/世界観の候補を複数出す（多様性を増やす）
- **選択（Selection）**: スコア（視聴維持/感情/映像化/分かりやすさ/一貫性）が最も高い案を採る
- **フレームワークは道具**: 英雄の旅などは「当てはめる公式」ではなく、見落とし防止・品質改善の手段

### 矛盾する記述とハイブリッド（混成）

複数文献に矛盾がある場合は、どちらかを選ぶだけでなく「分離して併記」「演出上の見せ方を変える」なども選択肢になる。

ただし、矛盾する複数ソースの要素を **同一シーン/設定として混成**する（ハイブリッド化する）場合は破綻リスクが高い。
スコアのために混成が必要なら、確定前に必ずユーザーへ承認を求める（衝突点・混ぜたい要素・スコア理由・リスクと安全策を提示し、Yes/No を取る）。

---

## 参考フレームワーク：ヒーローズジャーニー

### 理論的背景

ヒーローズジャーニー（英雄の旅）は、1949年にジョセフ・キャンベルが『千の顔を持つ英雄』で体系化した普遍的物語構造。ジョージ・ルーカスがスターウォーズ制作に活用し、現代エンターテインメントの基礎となった。

**核心原理**: 人間は「変容」の物語に本能的に惹かれる。

### 3フェーズ構造（圧縮版）

17段階 → 12段階 → 8段階 → **3要素**に圧縮

```
┌──────────────────────────────────────────────────────────────┐
│  [日常世界]  →  [試練/変容]  →  [新しい自分での帰還]        │
│   (0-10%)        (10-85%)          (85-100%)                 │
└──────────────────────────────────────────────────────────────┘
```

| フェーズ | 割合 | 目的 | 必須要素 |
|---------|------|------|----------|
| **日常世界** | 0-10% | フック、共感 | 視聴者が「自分ごと」と感じる状況 |
| **試練/変容** | 10-85% | 緊張、発見 | 問題→格闘→洞察 の流れ |
| **帰還** | 85-100% | 満足、余韻 | 変容後の姿、学びの提示 |

### Dan Harmon ストーリーサークル（8段階）

より詳細な構造が必要な場合：

```
        1. 快適圏にいる (0%)
              ↓
    8. 変化している ← 2. 何かを望む (12.5%)
         (100%)          ↓
              ↑      3. 未知に入る (25%)
    7. 帰還する           ↓
       (87.5%)      4. 適応する (37.5%)
              ↑           ↓
    6. 代償を払う → 5. 望みを得る (50%)
       (62.5%)
```

### キャンベル17段階（完全版）

長尺コンテンツや詳細設計が必要な場合：

| 幕 | 段階 | 名称 | 割合目安 |
|----|------|------|----------|
| **第1幕: 出発** | 1 | 日常世界 | 0-5% |
| | 2 | 冒険への召命 | 5-10% |
| | 3 | 召命の拒否 | 10-12% |
| | 4 | 賢者との出会い | 12-15% |
| | 5 | 第一関門の通過 | 15-20% |
| **第2幕: イニシエーション** | 6 | 試練・仲間・敵 | 20-35% |
| | 7 | 最深部への接近 | 35-45% |
| | 8 | 最大の試練 | 45-55% |
| | 9 | 報酬 | 55-65% |
| **第3幕: 帰還** | 10 | 帰路 | 65-75% |
| | 11 | 復活 | 75-90% |
| | 12 | 霊薬を持っての帰還 | 90-100% |

---

## 感情設計：エモーショナル・ローラーコースター

### 理論的背景

感情設計は、アリストテレスの『詩学』（紀元前335年頃）のカタルシス理論に起源を持ち、現代のデータサイエンスにより6つの基本パターンに分類された。Kurt Vonnegutが1950年代に提唱した「Story Shapes」理論は、2016年のReagan et al.の研究で科学的に実証された。

**核心原理**: 観客の感情を意図的に上下させることで、深い没入と満足感を生み出す。

### 6つの基本的感情曲線

```
1. Rags to Riches（上昇）
   感情 ↗ 一貫した上昇

2. Tragedy（下降）
   感情 ↘ 一貫した下降

3. Man in Hole（下降→上昇）★最も人気
   感情 ↘ ↗ 逆境から回復

4. Icarus（上昇→下降）
   感情 ↗ ↘ 成功から没落

5. Cinderella（上昇→下降→上昇）
   感情 ↗ ↘ ↗ 上昇、挫折、最終的成功

6. Oedipus（下降→上昇→下降）
   感情 ↘ ↗ ↘ 下降、一時的希望、最終的悲劇
```

**「Man in Hole」型が最も人気である理由**: 人間は逆境からの復活を見たいという根源的欲求を持つ。これは希望と回復力への普遍的な共感を反映している。

### 緊張と弛緩のリズム

感情ジェットコースターの核心は、緊張（Tension）と弛緩（Release）の戦略的配置にある。

```
感情強度
 ↑
 │     ★ 緊張ピーク1    ★ 緊張ピーク2（より高い）
 │    /\               /\
 │   /  \             /  \          ★ クライマックス
 │  /    \           /    \        /\
 │ /      \弛緩     /      \弛緩  /  \
 │/        \       /        \    /    \
 │──────────\_____/──────────\__/      \解決
 │
 └──────────────────────────────────────────→ 時間
   0%      25%      50%      75%      100%
```

**設計原則**:
- 緊張の後には必ず弛緩を配置
- 各緊張ピークは前より高くする（エスカレーション）
- 弛緩の間に次の緊張の種を蒔く
- クライマックス前に「最も暗い瞬間」を配置

### Hitchcockの爆弾理論

「サスペンスは情報の非対称性から生まれる」

```
[弱いサスペンス] テーブルの下に爆弾 → 爆発 → 観客は15秒の驚き
[強いサスペンス] 観客に爆弾を見せる → 5分間の会話 → 観客は5分間の緊張
```

**適用**: 視聴者に「何かが起こる」ことを予告し、その実現を待たせる。

### ピクサー22のストーリーテリングルール（抜粋）

Emma Coats（ピクサー）が整理した感情設計の原則：

| # | ルール | 感情設計への示唆 |
|---|--------|-----------------|
| 1 | キャラクターの努力を描く（成功より試み） | 苦闘が共感を生む |
| 4 | Once upon a time... Every day... One day... Because of that... Until finally... | 感情の因果連鎖を構築 |
| 6 | キャラクターが得意なことと苦手なことを与える | 葛藤の源泉を設計 |
| 7 | 結末から逆算して設計 | 感情的到達点を先に決める |
| 16 | キャラクターを困難な状況に置いてから脱出方法を考える | 緊張を先に、解決は後 |
| 19 | 偶然は主人公を困難に陥れるのに使えるが、救出には使えない | 解決は主体的に |
| 22 | 自分の物語の核心は何か？最も経済的な表現を見つける | 感情的核心を明確に |

### 感情操作テクニック

#### 視覚による感情誘導

| 要素 | 感情効果 |
|------|---------|
| ローアングル | 威圧感、権力 |
| ハイアングル | 脆弱性、孤独 |
| クローズアップ | 親密さ、感情の強調 |
| ワイドショット | 孤立、圧倒的状況 |
| 暖色系 | 温かさ、安心 |
| 寒色系 | 冷たさ、不安 |

#### 音響による感情誘導

| 要素 | 感情効果 |
|------|---------|
| 低音の持続 | 不安、緊張 |
| 高音のスティンガー | 驚き、恐怖 |
| 沈黙 | 緊張の極大化、重要性 |
| テンポ加速 | 興奮、緊急性 |
| マイナーキー | 悲しみ、不安 |
| メジャーキー | 喜び、達成感 |

### 感情設計フレームワーク比較

| フレームワーク | 提唱者 | 年 | 特徴 | 最適用途 |
|--------------|-------|-----|------|---------|
| Paradigm | Syd Field | 1979 | Plot Point I/IIを軸 | 基本構造の理解 |
| Story | Robert McKee | 1997 | シーンごとの値変化 | 複雑な物語 |
| Save the Cat! | Blake Snyder | 2005 | 15の詳細ビート | 商業映画 |
| 22 Steps | John Truby | 2007 | 道徳的成長の強調 | キャラクター重視 |
| Emotional Structure | Peter Dunne | 2006 | 感情構造に特化 | 感情設計の深化 |
| 6 Arcs | Reagan et al. | 2016 | データ科学的分類 | パターン選択 |

### カタルシスの設計

カタルシス（感情の浄化）は物語の最終目標。

**構成要素**:
1. **蓄積**: 感情を段階的に構築
2. **臨界点**: 感情が限界に達する瞬間
3. **解放**: 蓄積された感情の放出
4. **余韻**: 解放後の新しい平衡状態

**配置**: 通常、物語の85-95%地点

---

## 物語生成プロセス

### Phase 1: 素材分析（Research解析）

Deep Research出力から物語素材を抽出する。

#### Step 1.1: 主人公の特定

```yaml
protagonist_candidates:
  - source: knowledge_graph.nodes (type: Person)
  - criteria:
      - 変容を経験した人物
      - 困難を乗り越えた人物
      - 視聴者が共感できる人物
```

#### Step 1.2: エンゲージメントフックの選定

```yaml
hook_selection:
  source: engagement.hooks
  priority:
    1. hidden_truth (隠された真実)
    2. counterintuitive (常識の逆)
    3. mystery (未解決の謎)
    4. emotional (感情的共鳴)
    5. controversy (論争)
```

#### Step 1.3: テンションポイントの抽出

```yaml
tension_source: engagement.tension_points
usage:
  - 対立する視点を物語の葛藤に変換
  - 「でも実は...」の転換点として使用
```

### Phase 2: 物語設計

#### Step 2.1: SCQA構造の活用

Deep Researchの `synthesis.scqa` を物語骨格に変換：

| SCQA要素 | 物語での役割 | 位置（割合） |
|----------|-------------|-------------|
| Situation | 日常世界の設定 | 0-5% |
| Complication | 問題・葛藤の提示 | 5-15% |
| Question | 視聴者の疑問喚起 | 15-25%（暗示） |
| Answer | 解決・洞察の提示 | 70-100% |

#### Step 2.2: So What チェーン適用

`synthesis.so_what_chain` を活用して、単なる事実を「意味のある洞察」に変換：

```
事実 → So What? → So What? → So What? → 最終洞察
                                          ↓
                                      物語のテーマ
```

#### Step 2.3: 感情曲線の設計

```
感情
 ↑
 │              ★ クライマックス
 │             / \
 │            /   \
 │           /     ★ 解決
 │  ★       /
 │   \     /
 │    ★  /
 │     \/
 │      ★ 葛藤深化
 │
 └──────────────────────────────→ 時間
   0%    25%    50%    75%   100%
```

### Phase 3: 脚本執筆

#### Step 3.1: オープニング（0-10%）

**目的**: 視聴者を早期に引き込む

**テクニック**:
- **疑問形**: 「なぜ〇〇は△△なのか？」
- **常識の否定**: 「〇〇は間違っている」
- **驚きの事実**: 「実は〇〇は△△だった」
- **感情的フック**: 「誰もが知っているあの物語の、誰も知らない真実」

**テンプレート**:
```
[視覚] 印象的なオープニングカット
[音声] フック文
[テキスト] 補助テロップ（必要に応じて）
```

#### Step 3.2: 本体（10-85%）

**構造**:
```
[問題提示] 10-25%
   ↓ 「でも...」「しかし...」
[葛藤深化] 25-50%
   ↓ 「そして...」「ついに...」
[転換点] 50-70%
   ↓ 「実は...」「だから...」
[解決への道] 70-85%
```

**視覚設計の原則**:
- 適度な頻度でカット変更（長さに応じて調整）
- 静止画の場合はズーム/パンで動きを追加
- テキストは読みやすいサイズと表示時間を確保

#### Step 3.3: エンディング（85-100%）

**目的**: 満足感と余韻

**テクニック**:
- **変容の可視化**: Before → After を明示
- **学びの提示**: 「だから〇〇なのだ」
- **オープンループ**: 次回への伏線（シリーズの場合）
- **循環構造**: 最初のシーンに戻る

### Phase 4: 品質検証

#### Step 4.1: 構造整合チェック（任意フレームワーク）

フレームワーク（英雄の旅など）は「当てはめて合否を出す」ためではなく、見落とし防止の道具。
必要なときだけ使い、物語の強み（登場人物/世界観/フック）を削らない。

```yaml
# 例: Hero's Journey を“チェックリスト”として使う場合（任意）
hero_journey_checklist:
  ordinary_world:
    present: true/false
    position: "0-10%"
  call_to_adventure:
    present: true/false
    type: question/problem/opportunity
  ordeal:
    present: true/false
    tension_level: 1-10
  transformation:
    present: true/false
    before_after_clear: true/false
  return:
    present: true/false
    satisfaction_level: 1-10

# 共通: 物語の整合性（推奨）
coherence_checklist:
  narration_visual_consistent: true/false
  cause_effect_clear: true/false
  character_motives_clear: true/false
  world_rules_consistent: true/false
```

#### Step 4.2: エンゲージメント品質チェック

```yaml
engagement_checklist:
  strong_opening: true/false  # 必須
  curiosity_maintained: true/false
  pacing_appropriate: true/false
  emotional_payoff: true/false
```

#### Step 4.3: 情報正確性チェック

```yaml
accuracy_checklist:
  facts_from_research: true/false
  source_confidence: 0.0-1.0
  claims_verified: true/false
  no_fabrication: true/false
```

---

### Phase 5: 視覚化価値パートへの handoff

`story.md` を確定した後、Scriptwriter に直接渡す前に
**Visual Value Ideator** が `visual_value.md` を作る。

目的:

- 物語本筋の外側にある「見たいもの」を中盤の視覚報酬として定義する
- 動画生成AIだからこそ、実写セット不要で壮大に見せられる要素を拾う
- 竜宮城の内部、禁忌の箱、異界の回廊のような
  **読者は知っているが細部を見たことがないもの** を強化する

運用ルール:

- 価値パートは原則として動画全体の `20% - 80%` に置く
- 1価値パートは `4-6` カット
- 各カットは `4` 秒
- ナレーションは入れず、映像だけで満足感を作る
- 文字説明ではなく、形 / 光 / 動き / 機構 / ショー性で価値を伝える

---

## 物語パターンライブラリ

### パターン1: 隠された真実型

```
[フック] 「誰もが知っている〇〇の、誰も知らない真実」
[展開] 常識の提示 → 「でも実は...」 → 隠された事実
[結末] 新しい理解、世界観の更新
```

**適用**: `engagement.hooks.type == "hidden_truth"` の場合

### パターン2: 逆説型

```
[フック] 「〇〇は△△だと思っていませんか？実は逆です」
[展開] 常識の否定 → 証拠の提示 → 真の理由
[結末] パラダイムシフト
```

**適用**: `engagement.hooks.type == "counterintuitive"` の場合

### パターン3: 謎解き型

```
[フック] 「なぜ〇〇は△△なのか？」
[展開] 謎の提示 → 手がかり1 → 手がかり2 → 解明
[結末] 「だから〇〇なのだ」
```

**適用**: `engagement.hooks.type == "mystery"` の場合

### パターン4: 英雄譚型

```
[フック] 「この人物が世界を変えた」
[展開] 困難な状況 → 決断 → 試練 → 勝利
[結末] 変容した姿、レガシー
```

**適用**: `knowledge_graph.nodes` に著名人物がいる場合

### パターン5: 感情共鳴型

```
[フック] 感情的な場面/言葉
[展開] 背景説明 → 感情の深化 → カタルシス
[結末] 普遍的な教訓
```

**適用**: `engagement.hooks.type == "emotional"` の場合

---

## 出力スキーマ

### 物語出力フォーマット

```yaml
# === メタ情報 ===
story_metadata:
  topic: "string"
  source_research: "output/<topic>_<timestamp>/research.md"
  created_at: "ISO8601"
  target_duration: null  # 秒数（任意、未指定可）
  pattern_used: "hidden_truth | counterintuitive | mystery | hero | emotional"

# === 物語構造 ===
story_structure:
  protagonist:
    name: "string"
    role: "string"
    source_node_id: "research内のnode id"

  journey:
    ordinary_world:
      description: "string"
      position_percent: 0-10

    call_to_adventure:
      trigger: "string"
      question_raised: "string"

    ordeal:
      challenge: "string"
      tension_elements:
        - "string"
      position_percent: 45-55

    transformation:
      before: "string"
      after: "string"
      insight: "string"

    return:
      resolution: "string"
      position_percent: 85-100

  theme:
    governing_thought: "string"
    universal_truth: "string"

  emotional_arc:
    type: "rags_to_riches | tragedy | man_in_hole | icarus | cinderella | oedipus"
    tension_peaks:
      - position_percent: 25
        intensity: 1-10
        description: "string"
      - position_percent: 50
        intensity: 1-10
        description: "string"
      - position_percent: 75
        intensity: 1-10
        description: "string"
    catharsis:
      position_percent: 85-95
      buildup_elements:
        - "string"
      release_trigger: "string"

# === 脚本 ===
script:
  scenes:
    - scene_id: 1
      position_percent: "0-10"
      phase: "opening"

      visual:
        description: "string"
        type: "image | video | text_overlay"
        motion: "zoom_in | zoom_out | pan_left | pan_right | static"

      audio:
        narration: "string"
        bgm: "string"
        sfx: "string"

      text_overlay:
        main: "string"
        sub: "string"

      hook_type: "question | statement | shock | emotion"

    - scene_id: 2
      position_percent: "10-25"
      phase: "development"
      # ... 以下同様

    - scene_id: 3
      position_percent: "25-55"
      phase: "ordeal"

    - scene_id: 4
      position_percent: "55-85"
      phase: "transformation"

    - scene_id: 5
      position_percent: "85-100"
      phase: "ending"

# === エンゲージメント設計 ===
engagement_design:
  primary_hook:
    type: "string"
    content: "string"
    source: "engagement.hooks[n]"
    position_percent: 0-5

  tension_arc:
    - position_percent: 15
      tension_level: 3
      element: "問題提示"
    - position_percent: 40
      tension_level: 7
      element: "葛藤深化"
    - position_percent: 55
      tension_level: 9
      element: "クライマックス"
    - position_percent: 90
      tension_level: 5
      element: "解決"

  retention_techniques:
    - technique: "open_loop"
      position_percent: 10
      description: "疑問を提示して答えを後回し"
    - technique: "pattern_interrupt"
      position_percent: 35
      description: "予想を裏切る展開"
    - technique: "circular_structure"
      position_percent: 95
      description: "最初のシーンに視覚的に戻る"

# === 品質スコア ===
quality_scores:
  engagement_potential: 0.0-1.0
  information_accuracy: 0.0-1.0
  emotional_impact: 0.0-1.0
  narrative_coherence: 0.0-1.0
  selection_quality: 0.0-1.0
  # フレームワークは任意の“道具”。当てはめのスコアで合否を出さない。
  framework_notes:
    hero_journey_fit: "high|medium|low|null"
    notes: "string"

  checklist:
    strong_opening: true
    # 物語パターンによっては名前/形が変わる（英雄の旅に限らない）
    ordeal_present: true
    transformation_clear: true
    facts_verified: true

# === ソース追跡 ===
sources:
  facts_used:
    - fact: "string"
      source: "research.facts.xxx"
      confidence: 0.0-1.0

  hooks_used:
    - hook: "string"
      source: "research.engagement.hooks[n]"

  claims:
    - claim: "string"
      verification: "verified | unverified | partially_verified"
      source: "string"
```

## Handoff Artifact: `visual_value.md`

Visual Value Ideator は `workflow/visual-value-template.yaml` を基に、
次のような構造で `visual_value.md` を作る。

```yaml
visual_value_metadata:
  topic: "string"
  source_research: "output/<topic>_<timestamp>/research.md"
  source_story: "output/<topic>_<timestamp>/story.md"
  created_at: "ISO8601"

value_parts:
  - part_id: "midroll_visual_payoff_01"
    title: "string"
    placement_window:
      start_percent: 20
      end_percent: 80
      preferred_percent: 50
      rationale: "string"
    why_this_matters:
      - "string"
    ai_visualization_advantage:
      no_physical_set_required: true
      spectacle_scale: "string"
      notes: "string"
    related_objects: ["object_id"]
    cut_plan:
      - cut_id: 1
        duration_seconds: 4
        narration: ""
        focus: "string"
        description: "string"
        viewer_payoff: "string"
```

---

## 代替フレームワーク

### ヒロインズジャーニー（女性主人公向け）

ヒーローズジャーニーが「上昇」構造なのに対し、ヒロインズジャーニーは「下降→再生→上昇」構造。

```
1. 男性的世界での成功への憧れ
2. 男性的成功の達成
3. 空虚さの認識
4. 下降（暗闘への旅）
5. 死（古い自己の死）
6. 女性的なものとの再接続
7. 男性的・女性的の統合
8. 帰還
```

**適用**: 女性主人公、内面の成長、自己発見がテーマの場合

### Save the Cat（15ビート）

より細かい構成管理が必要な場合：

| ビート | 位置 |
|--------|------|
| Opening Image | 0-1% |
| Theme Stated | 5% |
| Set-Up | 1-10% |
| Catalyst | 10% |
| Debate | 10-25% |
| Break into Two | 25% |
| B Story | 30% |
| Fun and Games | 30-50% |
| Midpoint | 50% |
| Bad Guys Close In | 50-75% |
| All Is Lost | 75% |
| Dark Night of the Soul | 75-80% |
| Break into Three | 80% |
| Finale | 80-99% |
| Final Image | 99-100% |

---

## 制約と注意事項

### コンテンツガイドライン

```yaml
constraints:
  narration:
    words_per_second: 3-4  # 日本語目安
    pacing: "コンテンツの長さに応じて調整"

  visual:
    maintain_interest: true
    appropriate_pacing: true

  accuracy:
    min_source_confidence: 0.7
    fabrication: prohibited
```

### 避けるべきパターン

1. **情報過多**: 詰め込みすぎない（1つのテーマに集中）
2. **抽象的すぎる**: 具体的なエピソード、数字、人物を使う
3. **フックの弱さ**: 冒頭で視聴者を失う
4. **変容の不在**: 「だから何？」で終わらない
5. **事実の捏造**: Research出力にない情報を勝手に追加しない

---

## 実行フロー

```
1. Research出力の読み込み
   └→ output/<topic>_<timestamp>/research.md

2. 素材分析
   ├→ 主人公候補の抽出
   ├→ エンゲージメントフック選定
   └→ テンションポイント抽出

3. 物語パターン選択
   └→ フックタイプに基づく最適パターン

4. SCQA骨格構築
   └→ research.synthesis.scqa を変換

5. 脚本執筆
   ├→ オープニング（0-10%）
   ├→ 本体（10-85%）
   └→ エンディング（85-100%）

6. 品質検証
   ├→ 構造整合（任意フレームワーク）
   ├→ エンゲージメント品質
   └→ 情報正確性

7. 出力
   └→ output/<topic>_<timestamp>/story.md
```

---

## 参考文献

### 物語構造理論

- Campbell, Joseph. *The Hero with a Thousand Faces*. 1949.
- Vogler, Christopher. *The Writer's Journey: Mythic Structure for Writers*. 1992.
- Murdock, Maureen. *The Heroine's Journey*. 1990.
- Snyder, Blake. *Save the Cat!*. 2005.

### 感情設計理論

- Aristotle. *Poetics*. 紀元前335年頃.（カタルシス理論の原典）
- Field, Syd. *Screenplay: The Foundations of Screenwriting*. 1979.
- McKee, Robert. *Story: Substance, Structure, Style, and the Principles of Screenwriting*. 1997.
- Truby, John. *The Anatomy of Story: 22 Steps to Becoming a Master Storyteller*. 2007.
- Dunne, Peter. *Emotional Structure: Creating the Story Beneath the Plot*. 2006.
- Reagan, A.J. et al. "The emotional arcs of stories are dominated by six basic shapes." *EPJ Data Science*. 2016.

### 応用ガイド

- [Chris Vogler's Short Form Guide](https://chrisvogler.wordpress.com/2011/02/24/heros-journey-short-form/)
- [Dan Harmon's Story Circle](https://reedsy.com/blog/guide/story-structure/dan-harmon-story-circle/)
- [No Film School - Pixar 22 Rules](https://nofilmschool.com/2012/06/22-rules-storytelling-pixar)
- [MIT Technology Review - Six Emotional Arcs](https://www.technologyreview.com/2016/07/06/158961/data-mining-reveals-the-six-basic-emotional-arcs-of-storytelling/)

### 分析事例

- [The Script Lab - Star Wars Hero's Journey](https://thescriptlab.com/features/screenwriting-101/12309-the-heros-journey-breakdown-star-wars/)
- [神話の法則を千と千尋で解説](https://kkusaba.com/heros-journey/)
