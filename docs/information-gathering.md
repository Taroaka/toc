# 情報収集手順書（Deep Research System）

## 概要

ユーザーが入力したトピックに対して、多角的・多層的に情報を収集し、構造化された知識ベースを生成するシステム。

### 関連ドキュメント

- `docs/orchestration-and-ops.md`（全体制御・品質保証・配信/改善ループ）

```
[トピック入力] → [初期仮説設定] → [イシューツリー構築] → [優先順位付け]
      ↓
[二次情報収集] → [ギャップ特定] → [一次情報収集] → [MECE検証]
      ↓
[So Whatテスト] → [オントロジーマッピング] → [フック抽出] → [構造化知識ベース]
```

## 設計原則

## 必須: ストーリー基礎の確定（Story-first）

調査が「裏話・小ネタ」へ過度に偏ると、後段の story/script が破綻しやすい。
そのため本システムでは、**最初に「そもそもどんな話か」**を明確にし、次に検証・深掘りへ進む。

### 最優先アウトプット（必須）

- **canonical story dump**（原話・通俗版・重要版を、省略しすぎず物語として厚く書く）
- **chronological events**（scene ではなく、出来事単位の時系列素材）
- **characters / relationships / motivations**（人物、関係、欲求、対立、賭け金、舞台）
- **variants / conflicts / selection cues**（版差、矛盾、採用候補、混成の可否）
- **source passages / evidence notes / confidence**（出典、短い根拠抜粋、信頼度）
- **symbols / themes / emotional material / adaptation options**（象徴、主題、感情素材、映像化・物語化の選択肢）
- **open questions / unverified items**（未検証点と追加調査タスク）

### 禁止（アンチパターン）

- canonical synopsis が曖昧なまま、裏話・逸話・小ネタ・派生作品の話題を先行させる
- 特定の公式（英雄の旅など）への当てはめ“だけ”を先に語り、肝心の**ストーリーの骨**が出力されていない

### フレームワーク検証は「骨」が確定してから（任意）

英雄の旅などのフレームワーク検証は、上記の beat sheet を根拠に行う（推測だけで結論しない）。
ただし目的は「公式に当てはめて合否を出す」ことではなく、**見落とし防止の道具**として使うに留める。

また、複数文献に矛盾がある場合は、後段（story/script）が **創造→選択**で高得点を狙えるように、
矛盾点（A説/B説）と選択肢（分離/片方採用/混成の可否）を整理して残す。
同一シーン/設定として矛盾要素を **ハイブリッド（混成）**する案は高得点になり得る一方で破綻リスクが高いため、
混成を確定させる必要がある場合は **人間承認が必要**（運用）。

## 任意: p200 向けの使い所メモ（Suggested story usage）

調査段階の主責務は、後続が削れるだけの物語素材を増やすことにある。
scene 分割、感情曲線、候補比較、採用判断は p200 / story stage の主責務とする。

p100 で「この素材は opening 向き」「終盤の葛藤に効く」などの見立てがある場合は、
`suggested_story_usage` に任意メモとして残してよい。ただし `scene_plan` や各項目の `scene_ids` は必須ではない。

### ルール（運用）

- p100 では scene 数を確定しない
- `scene_plan` は任意・参考情報として扱い、評価必須項目にしない
- p200 は p100 の `story_materials` / `conflicts` / `source_passages` から scene / beat / emotion curve を作る
- p100 で scene_id を付ける場合も、後続の採用判断を拘束しない

### 期待する出力

- `story_materials`（原話、出来事、人物、象徴、感情素材）
- `source_inventory` / `source_passages`（出典棚卸しと根拠抜粋）
- `variants` / `conflicts`（版差と選択材料）
- `handoff_to_story`（p200 が何を選び、何に注意すべきか）
- `suggested_story_usage`（任意。opening / midpoint / ending などの粗い使い所）

## 推奨: 出力量の目安（後から削る前提）

この段階は情報を「増やせる」のが最大の価値。後段で削れるよう、まず厚めに出す。

目安（トピックの難易度で増減）:

- sources: **12–30件**（URL/出典名を必ず残す）
- story materials:
  - canonical story dump: **20–60行**
  - chronological events: **20–40個**
  - characters / relationships / motivations: 主要人物と関係を網羅
- source passages: **10–30個**（短い抜粋、source_id、confidence）
- conflicts / variants: **3–10個**
- hooks: 10–25個（scene_id ではなく、使い所や支える facts を任意で付ける）
- facts: 30–80個（各factに sources + confidence）

テンプレ運用:

- 最小: `workflow/research-template.yaml`
- 推奨（厚め）: `workflow/research-template.production.yaml`

### 教科書的網羅性（Comprehensive Coverage）

- **MECE原則**: Mutually Exclusive, Collectively Exhaustive（漏れなくダブりなく）
- **Bloom's Taxonomy**: 認知レベルの階層的整理
- **オントロジー**: エンティティと関係性の形式的定義

### エンゲージメント価値（Engagement Value）

- **Curiosity Gap**: 「知っていること」と「知りたいこと」のギャップ
- **Open Loop**: 未解決の問いによる興味維持
- **Tension Points**: 対立・論争による緊張感

### コンサル手法（Consulting Methodology）

- **仮説駆動**: データ収集前に仮説を立て、検証しながら進める
- **イシューツリー**: 問題を構造化し、優先順位をつけて効率的に収集
- **So What テスト**: 「だから何？」を繰り返し、本質的示唆を抽出
- **ピラミッド原則**: ボトムアップで統合、トップダウンで提示

## 仮説駆動型フレームワーク

### 初期仮説の設定

トピック入力後、網羅的収集の前に初期仮説を設定する。

```yaml
hypothesis_framework:
  # 初期仮説
  initial_hypothesis:
    statement: string           # 仮説文
    rationale: string           # 仮説を立てた根拠
    assumptions:                # 仮説が正しいための前提条件
      - assumption: string
        testable: boolean       # 検証可能か

  # 仮説ツリー（仮説を分解）
  hypothesis_tree:
    root: string                # ルート仮説
    branches:
      - branch_hypothesis: string
        sub_hypotheses:
          - hypothesis: string
            validation_method: string   # 検証方法
            data_needed: string         # 必要なデータ
            priority: high|medium|low

  # 検証状態の追跡
  validation_tracking:
    - hypothesis: string
      status: validated|refuted|partial|pending
      evidence:
        - finding: string
          source: string
          supports: boolean     # 仮説を支持するか
      confidence: float
      next_action: string       # 次のアクション
```

### 仮説設定のガイドライン

| ステップ | 内容 | 例（桃太郎） |
|---------|------|-------------|
| 1. 初期仮説 | トピックの本質についての仮説 | 「桃太郎は古代の政治的出来事を反映した民話である」 |
| 2. 前提条件 | 仮説が正しいために必要な条件 | 「成立時期と歴史的事件が一致する」「地名に対応がある」 |
| 3. 検証方法 | 各前提をどう検証するか | 「学術論文で成立時期を確認」「地名の語源を調査」 |
| 4. 優先順位 | インパクト×検証容易性で優先度 | 「成立時期」= High、「地名対応」= Medium |

## イシューツリー

### 問題の構造化

トピックを検証可能な論点に分解する。

```yaml
issue_tree:
  root_question: string         # 根本の問い

  branches:
    - issue: string             # 論点
      type: what|why|how        # 論点タイプ
      sub_issues:               # 下位論点
        - issue: string
          sub_issues: []

      # 収集計画
      data_plan:
        source_type: primary|secondary
        specific_sources: [string]
        expected_effort: high|medium|low

      # 状態管理
      status: not_started|in_progress|answered|blocked
      answer: string            # 回答（判明後）
      confidence: float
```

### イシューツリーの構築方法

```
4つの分解レンズ:
├── Stakeholder（利害関係者）: 誰の視点で見るか
├── Process（プロセス）: どの段階・工程か
├── Segment（セグメント）: どの分類・カテゴリか
└── Math（数式分解）: 構成要素に分解
```

### 例：桃太郎のイシューツリー

```
Q: 桃太郎とは何か？（根本の問い）
├── Q1: 物語の内容は？ [What]
│   ├── Q1-1: 原典のストーリーは？
│   ├── Q1-2: 登場人物は？
│   └── Q1-3: バリエーションは？
├── Q2: なぜこの物語が生まれたか？ [Why]
│   ├── Q2-1: 歴史的背景は？
│   ├── Q2-2: 文化的意味は？
│   └── Q2-3: 類似の物語は？
├── Q3: どのように伝承されてきたか？ [How]
│   ├── Q3-1: 地域差は？
│   ├── Q3-2: 時代による変化は？
│   └── Q3-3: 現代での扱いは？
└── Q4: なぜ今も人気があるか？ [Why]
    ├── Q4-1: 普遍的テーマは？
    ├── Q4-2: 教育的価値は？
    └── Q4-3: エンタメ展開は？
```

## 収集優先順位付け

### 優先度マトリクス

```yaml
prioritization:
  criteria:
    impact:           # 仮説検証へのインパクト
      high: 3
      medium: 2
      low: 1
    effort:           # 収集の労力
      high: 3
      medium: 2
      low: 1
    availability:     # 情報の入手可能性
      high: 3
      medium: 2
      low: 1

  formula: "(impact * availability) / effort"

  priority_matrix:
    - item: string
      impact: high|medium|low
      effort: high|medium|low
      availability: high|medium|low
      score: float
      action: collect_now|collect_later|skip|delegate
```

### 優先順位の決定フロー

```
1. 各論点に impact/effort/availability を評価
2. スコア算出: (impact × availability) ÷ effort
3. スコア順にソート
4. 上位からリソースを割り当て

判断基準:
- score ≥ 3.0 → collect_now（即時収集）
- score 1.5-3.0 → collect_later（後回し）
- score < 1.5 → skip（スキップ）または delegate（委任）
```

## 情報収集の階層

### 二次情報（Secondary Research / デスクリサーチ）

既存の公開情報から収集。**最初に実施**。

#### Level 1: 原典・一次資料

最優先で取得。全文テキストの確保を目指す。

| ソース | 対象 | API/取得方法 |
|--------|------|-------------|
| 青空文庫 | 著作権切れ日本文学 | API / GitHub Raw |
| 国立国会図書館デジタル | 古典・歴史資料 | NDL Search API |
| 古典籍総合データベース | 古典籍画像・翻刻 | NIJL API |
| Project Gutenberg | 著作権切れ英語文学 | API / Mirror |
| Internet Archive | 書籍・音声・映像 | API |

#### Level 2: 学術・研究

学術的な裏付け・解釈を取得。

| ソース | 対象 | API/取得方法 |
|--------|------|-------------|
| CiNii Research | 日本の学術論文 | CiNii API |
| J-STAGE | 学術誌・紀要 | J-STAGE API |
| Google Scholar | 学術論文全般 | SerpAPI / スクレイピング |
| 大学リポジトリ | 学位論文・研究成果 | OAI-PMH |
| JSTOR | 海外学術誌 | JSTOR API |

#### Level 3: 百科事典・解説

基礎情報・構造化データを取得。

| ソース | 対象 | API/取得方法 |
|--------|------|-------------|
| Wikipedia | 概要・解説（多言語） | MediaWiki API |
| Wikidata | 構造化データ・関連性 | SPARQL / API |
| コトバンク | 国語辞典・百科事典 | スクレイピング |
| ブリタニカ | 専門的解説 | API / スクレイピング |
| DBpedia | Wikipedia構造化版 | SPARQL |

#### Level 4: 考察・解釈・民間知識

多様な視点・解釈を取得。

| ソース | 対象 | API/取得方法 |
|--------|------|-------------|
| Web検索 | ブログ・記事・考察 | Google/Bing API |
| Reddit | 海外の議論・考察 | Reddit API |
| Quora | Q&A形式の知識 | スクレイピング |
| YouTube | 解説動画トランスクリプト | YouTube Data API |
| note/Zenn | 日本語の考察記事 | スクレイピング |

### 一次情報（Primary Research）

二次情報で埋められないギャップを直接収集。

```yaml
primary_research:
  # エキスパートインタビュー
  expert_interviews:
    - expert_type: string       # 専門家タイプ（学者、実務家等）
      expertise_area: string    # 専門領域
      interview_objectives:     # インタビュー目的
        - objective: string
          related_issue: string # 対応するイシュー

      # 質問設計（オープンエンド、広→狭）
      questions:
        - question: string
          type: broad|specific|probing
          expected_insight: string

      # 結果
      key_insights: [string]
      quotes: [string]
      follow_up_needed: boolean

  # フィールド観察
  field_observations:
    - location: string
      objective: string
      observations:
        - observation: string
          interpretation: string
      artifacts_collected: [string]  # 収集物

  # アンケート調査
  surveys:
    - target_population: string
      sample_size: int
      methodology: string
      key_questions: [string]
      key_findings:
        - finding: string
          statistical_significance: float
```

### エキスパートインタビューのベストプラクティス

| 原則 | 説明 |
|------|------|
| **事前準備** | 二次情報で答えられる質問は事前に除外 |
| **構造化** | 広い質問 → 具体的質問へ流れるように設計 |
| **オープンエンド** | Yes/No で終わらない質問を使う |
| **中立性** | 誘導せず、客観的な入力を得る |
| **深掘り** | 「なぜ？」「具体的には？」で掘り下げる |

## So What テスト（示唆抽出）

### ピラミッド原則に基づく統合

収集した情報から本質的な示唆を抽出する。

```yaml
synthesis:
  # 生の発見事項
  raw_findings:
    - finding: string
      source: string
      reliability: float

  # So What の連鎖（3回繰り返す）
  so_what_chain:
    - finding: string           # 発見事項
      so_what_1: string         # だから何？（1段目：直接的意味）
      so_what_2: string         # だから何？（2段目：より広い意味）
      so_what_3: string         # だから何？（3段目：本質的示唆）
      final_insight: string     # 最終的な示唆

  # グルーピングと統合
  insight_groups:
    - group_theme: string       # グループテーマ
      supporting_findings: [string]
      synthesized_insight: string
      confidence: float

  # 統括的結論（Governing Thought）
  governing_thought: string     # 一言で言うと何か

  # SCQA構造
  scqa:
    situation: string           # 状況（誰もが同意する前提）
    complication: string        # 問題（何が課題か）
    question: string            # 問い（何を解決すべきか）
    answer: string              # 答え（結論・提言）
```

### So What テストの実行方法

```
発見: 「桃太郎の最古の文献は室町時代末期」
  ↓ So What?
意味1: 「500年以上の歴史がある」
  ↓ So What?
意味2: 「日本人に長く愛されてきた普遍的な物語」
  ↓ So What?
示唆: 「時代を超えて共感される要素がある → それは何か？」
```

### SCQA フレームワーク

| 要素 | 説明 | 例（桃太郎研究） |
|------|------|-----------------|
| **Situation** | 前提・背景 | 桃太郎は日本で最も有名な昔話の一つである |
| **Complication** | 問題・課題 | しかし、その起源や本来の意味は諸説あり不明確 |
| **Question** | 問い | 桃太郎の本質的な意味と価値は何か？ |
| **Answer** | 答え・結論 | 桃太郎は○○を象徴する物語であり、現代においても○○の価値がある |

## オントロジー定義

### エンティティタイプ

```yaml
entity_types:
  Person:
    properties:
      - name: string
      - aliases: [string]
      - era: string
      - role: string
      - description: string

  Place:
    properties:
      - name: string
      - coordinates: [lat, lon]
      - significance: string
      - current_status: string

  Event:
    properties:
      - name: string
      - date: string
      - description: string
      - participants: [Person]
      - location: Place

  Concept:
    properties:
      - name: string
      - definition: string
      - domain: string
      - related_concepts: [Concept]

  Work:
    properties:
      - title: string
      - type: string  # 小説/映画/漫画/歌など
      - creator: Person
      - created_date: string
      - description: string
```

### 関係性タイプ

```yaml
relationship_types:
  # 因果関係
  - caused_by: "AはBによって引き起こされた"
  - led_to: "AはBにつながった"

  # 影響関係
  - influenced_by: "AはBに影響を受けた"
  - inspired: "AはBに影響を与えた"

  # 空間関係
  - located_in: "AはBに位置する"
  - originated_from: "AはBを起源とする"

  # 時間関係
  - preceded_by: "AはBの前に起きた"
  - followed_by: "AはBの後に起きた"
  - contemporary_with: "AはBと同時代"

  # 派生関係
  - derived_from: "AはBから派生した"
  - variant_of: "AはBの変形である"

  # 所属関係
  - part_of: "AはBの一部である"
  - contains: "AはBを含む"

  # 対立関係
  - contrasts_with: "AはBと対照的である"
  - contradicts: "AはBと矛盾する"
```

## MECE検証フレームワーク

収集した知識が「漏れなくダブりなく」かを検証する。

### 検証次元

```yaml
mece_dimensions:
  temporal:           # 時間軸
    - past            # 起源・歴史
    - present         # 現在の状況・解釈
    - future          # 影響・展望

  perspective:        # 視点
    - protagonist     # 主体・主人公視点
    - antagonist      # 対立者・敵役視点
    - observer        # 第三者・傍観者視点
    - meta            # メタ・作者視点

  abstraction:        # 抽象度
    - concrete        # 具体的事実
    - interpretive    # 解釈・分析
    - meta            # メタ分析・批評

  source_type:        # 情報源タイプ
    - primary         # 一次資料
    - secondary       # 二次資料（学術）
    - tertiary        # 三次資料（百科事典）
    - informal        # 非公式（ブログ等）

  sentiment:          # 感情・評価
    - positive        # 肯定的
    - neutral         # 中立
    - negative        # 否定的・批判的
```

### 検証プロセス

```
1. 収集した情報を各次元でタグ付け
2. 次元ごとのカバレッジを算出
3. ギャップ（未収集の観点）を特定
4. 重複（同一内容の重複）を検出
5. ギャップに対して追加収集を実行
```

## エンゲージメントフック抽出

各情報から「興味を引くポイント」を抽出・タグ付けする。

### フックタイプ

```yaml
hook_types:
  mystery:            # 謎・未解明
    description: "未だ解明されていない謎"
    example: "なぜ桃から生まれたのか、諸説あり決着していない"
    curiosity_trigger: "答えを知りたい"

  counterintuitive:   # 直感に反する
    description: "常識や直感に反する事実"
    example: "鬼は実は被害者だった説がある"
    curiosity_trigger: "本当に？詳しく知りたい"

  hidden_truth:       # 隠された真実
    description: "あまり知られていない事実"
    example: "99%の人が知らない桃太郎の原典では..."
    curiosity_trigger: "自分は知らない側かも"

  emotional:          # 感情を揺さぶる
    description: "感動・恐怖・驚きなど感情に訴える"
    example: "桃太郎の本当の結末は悲劇だった"
    curiosity_trigger: "感情的に惹きつけられる"

  connection:         # 意外なつながり
    description: "予想外の関連性"
    example: "桃太郎と古代ペルシャ神話の共通点"
    curiosity_trigger: "そんなつながりが？"

  controversy:        # 論争・対立
    description: "専門家の間でも意見が分かれる"
    example: "桃太郎の起源は岡山か香川か、論争が続く"
    curiosity_trigger: "どちらが正しいのか"
```

### Curiosity Score算出

```
curiosity_score = (
    novelty_factor      * 0.3 +   # 新規性（知られていない度合い）
    emotional_impact    * 0.25 +  # 感情的インパクト
    controversy_level   * 0.2 +   # 議論の余地
    relatability        * 0.15 +  # 共感・関連性
    actionability       * 0.1     # 「誰かに話したい」度
)
```

## 認知レベルタグ（Bloom's Taxonomy）

情報を認知レベルで分類し、深さのバランスを確認する。

```yaml
cognitive_levels:
  remember:           # 記憶：事実の想起
    description: "基本的な事実・データ"
    examples:
      - "桃太郎は室町時代末期に成立"
      - "主要キャラクターは桃太郎、犬、猿、雉"

  understand:         # 理解：意味の把握
    description: "事実の背景・理由の理解"
    examples:
      - "桃が選ばれた理由は中国の桃信仰に由来"
      - "きびだんごは吉備国（岡山）との関連を示唆"

  apply:              # 応用：知識の適用
    description: "他の文脈への適用"
    examples:
      - "桃太郎の構造は他の英雄譚にも見られる"
      - "現代のコンテンツにおける桃太郎モチーフ"

  analyze:            # 分析：構造の解明
    description: "要素間の関係性分析"
    examples:
      - "桃太郎の物語構造はキャンベルの英雄の旅に従う"
      - "登場人物の象徴的意味の分析"

  evaluate:           # 評価：判断・批評
    description: "価値判断・批評"
    examples:
      - "柳田國男の解釈 vs 現代の再解釈の比較評価"
      - "芥川龍之介版の文学的価値"

  create:             # 創造：新たな生成
    description: "新しい視点・解釈の創出"
    examples:
      - "現代社会における桃太郎の新解釈"
      - "異なる文化圏との比較から見える新たな意味"
```

## 構造化スキーマ

### 完全版スキーマ

```yaml
# === 基本情報 ===
topic: string
aliases: [string]

# === 仮説駆動 ===
hypothesis:
  initial_hypothesis:
    statement: string
    rationale: string
    assumptions:
      - assumption: string
        testable: boolean
  hypothesis_tree:
    root: string
    branches:
      - branch_hypothesis: string
        sub_hypotheses:
          - hypothesis: string
            validation_method: string
            data_needed: string
            priority: high|medium|low
  validation_tracking:
    - hypothesis: string
      status: validated|refuted|partial|pending
      evidence:
        - finding: string
          source: string
          supports: boolean
      confidence: float

# === イシューツリー ===
issue_tree:
  root_question: string
  branches:
    - issue: string
      type: what|why|how
      sub_issues: []
      data_plan:
        source_type: primary|secondary
        specific_sources: [string]
        expected_effort: high|medium|low
      status: not_started|in_progress|answered|blocked
      answer: string
      confidence: float

# === 優先順位 ===
prioritization:
  - item: string
    impact: high|medium|low
    effort: high|medium|low
    availability: high|medium|low
    score: float
    action: collect_now|collect_later|skip

# === 原典情報 ===
primary_source:
  full_text: string
  source: string
  source_url: string
  original_date: string
  author: string
  variants:
    - version_name: string
      differences: string
      source: string

# === 一次情報収集 ===
primary_research:
  expert_interviews:
    - expert_type: string
      expertise_area: string
      questions: [string]
      key_insights: [string]
  field_observations:
    - location: string
      observations: [string]
  surveys:
    - target: string
      sample_size: int
      key_findings: [string]

# === 知識グラフ ===
knowledge_graph:
  nodes:
    - id: string
      type: Person|Place|Event|Concept|Work
      label: string
      properties: {}
  edges:
    - from: node_id
      to: node_id
      relation: string
      description: string
      source: string

# === 事実情報 ===
facts:
  origin:
    description: string
    sources: [string]
    confidence: float
  timeline:
    - date: string
      event: string
      source: string
      cognitive_level: string
  geography:
    - place: string
      relevance: string
      coordinates: [lat, lon]
  people:
    - name: string
      role: string
      description: string

# === 解釈・考察 ===
interpretations:
  academic:
    - claim: string
      author: string
      source: string
      year: int
      cognitive_level: string
  cultural:
    - aspect: string
      description: string
      source: string
  controversies:
    - topic: string
      positions: [string]
      sources: [string]
      resolution_status: string

# === 関連情報 ===
connections:
  related_works:
    - title: string
      type: string
      relation: string
  influences:
    - direction: gave|received
      target: string
      description: string
  cross_references:
    - topic: string
      relation: string

# === So What 統合 ===
synthesis:
  raw_findings: [string]
  so_what_chain:
    - finding: string
      so_what_1: string
      so_what_2: string
      so_what_3: string
      final_insight: string
  insight_groups:
    - group_theme: string
      supporting_findings: [string]
      synthesized_insight: string
  governing_thought: string
  scqa:
    situation: string
    complication: string
    question: string
    answer: string

# === エンゲージメント価値 ===
engagement:
  hooks:
    - type: mystery|counterintuitive|hidden_truth|emotional|connection|controversy
      content: string
      target_emotion: string
      curiosity_score: float
  tension_points:
    - topic: string
      positions: [string]
      narrative_potential: string
  open_questions:
    - question: string
      known_theories: [string]
      investigation_status: string

# === MECE検証結果 ===
mece_coverage:
  dimensions:
    temporal:
      past: float
      present: float
      future: float
    perspective:
      protagonist: float
      antagonist: float
      observer: float
    abstraction:
      concrete: float
      interpretive: float
      meta: float
  gaps:
    - dimension: string
      value: string
      priority: high|medium|low
  overlaps:
    - items: [string]
      action: merge|keep_both|discard

# === 認知レベル分布 ===
cognitive_distribution:
  remember: int
  understand: int
  apply: int
  analyze: int
  evaluate: int
  create: int

# === メタ情報 ===
metadata:
  collected_at: datetime
  sources_used: [string]
  confidence_score: float
  completeness_score: float
  engagement_score: float
  hypothesis_validation_rate: float  # 仮説検証率
```

## 収集プロセス

### Step 1: トピック正規化

```
入力: "桃太郎"
    ↓
正規化処理:
  - 別名展開: ["桃太郎", "ももたろう", "Momotaro", "Momotarō"]
  - 関連キーワード: ["桃太郎伝説", "桃太郎神社", "鬼ヶ島"]
  - ドメイン推定: "日本昔話", "民話", "伝承"
  - オントロジータイプ推定: Work (物語作品)
```

### Step 2: 初期仮説設定

```
トピックについて:
1. 初期仮説を1-3個設定
2. 各仮説の前提条件を列挙
3. 検証方法を特定
4. 仮説ツリーを構築
```

### Step 3: イシューツリー構築

```
1. 根本の問い（Root Question）を設定
2. What/Why/How で分解
3. 各論点を2-3階層で詳細化
4. MECEを確認
```

### Step 4: 優先順位付け

```
各論点に対して:
1. Impact（仮説検証へのインパクト）を評価
2. Effort（収集労力）を評価
3. Availability（入手可能性）を評価
4. スコア算出: (Impact × Availability) ÷ Effort
5. 優先順位でソート
```

### Step 5: 二次情報収集（デスクリサーチ）

```
優先順位に従って:
[Level 1: 原典] ──┐
[Level 2: 学術] ──┼──→ [情報プール]
[Level 3: 百科] ──┤
[Level 4: 考察] ──┘
```

### Step 6: ギャップ特定

```
収集した情報を分析:
1. イシューツリーの未回答論点を特定
2. 仮説検証に不足しているエビデンスを特定
3. MECE次元でのカバレッジギャップを特定
4. 一次情報が必要な項目をリストアップ
```

### Step 7: 一次情報収集

```
ギャップを埋めるために:
1. エキスパートインタビューの実施
2. フィールド観察（必要な場合）
3. アンケート調査（必要な場合）
4. 結果を情報プールに追加
```

### Step 8: MECE検証

```
1. 各次元でカバレッジを算出
2. ギャップを特定 → gaps に記録
3. 重複を検出 → overlaps に記録
4. 優先度の高いギャップに対して追加収集
```

### Step 9: So What テスト

```
収集した情報に対して:
1. 各発見事項に「So What?」を3回適用
2. 最終的な示唆を抽出
3. 関連する示唆をグルーピング
4. 統括的結論（Governing Thought）を導出
5. SCQA構造で整理
```

### Step 10: オントロジーマッピング

```
収集した情報から:
1. エンティティを抽出 → nodes に追加
2. 関係性を特定 → edges に追加
3. 知識グラフを構築
```

### Step 11: フック抽出

```
収集した情報から:
1. 謎・未解明点を抽出 → hooks (mystery)
2. 直感に反する事実を抽出 → hooks (counterintuitive)
3. 論争点を抽出 → tension_points
4. 未解決の問いを抽出 → open_questions
5. curiosity_score を算出
```

### Step 12: 認知レベル分類

```
各情報に対して:
1. Bloom's Taxonomy でレベルを判定
2. cognitive_level タグを付与
3. 分布を cognitive_distribution に集計
4. バランスが偏っていれば追加収集
```

### Step 13: 構造化・統合

```
[情報プール] → [スキーママッピング] → [構造化知識ベース]
                      ↓
              重複排除・正規化
                      ↓
              スコア算出:
              - confidence_score
              - completeness_score
              - engagement_score
              - hypothesis_validation_rate
```

## 品質基準

### 必須フィールド

以下は必ず取得を試みる：

- `topic` - トピック名
- `hypothesis.initial_hypothesis` - 初期仮説
- `issue_tree.root_question` - 根本の問い
- `primary_source.full_text` または `primary_source.source` - 原典情報
- `facts.origin` - 起源・成立情報
- `synthesis.governing_thought` - 統括的結論
- `knowledge_graph.nodes` - 最低3つのエンティティ
- `engagement.hooks` - 最低2つのフック
- `metadata.sources_used` - 使用ソース一覧

### 信頼度スコアリング

| スコア | 基準 |
|--------|------|
| 0.9-1.0 | 一次資料から直接取得 |
| 0.7-0.9 | 学術論文・公式情報源 |
| 0.5-0.7 | Wikipedia等の編集済み百科事典 |
| 0.3-0.5 | 個人ブログ・考察（複数一致） |
| 0.0-0.3 | 単一の非公式ソース |

### 完全性スコアリング（MECE）

| スコア | 基準 |
|--------|------|
| 0.9-1.0 | 全次元で80%以上カバー、ギャップなし |
| 0.7-0.9 | 主要次元でカバー、軽微なギャップあり |
| 0.5-0.7 | 一部次元に明確なギャップ |
| 0.3-0.5 | 複数次元でギャップ |
| 0.0-0.3 | 大部分が未収集 |

### エンゲージメントスコアリング

| スコア | 基準 |
|--------|------|
| 0.9-1.0 | 5種類以上のフック、高curiosity_score |
| 0.7-0.9 | 3-4種類のフック、tension_pointあり |
| 0.5-0.7 | 2種類のフック |
| 0.3-0.5 | 1種類のフックのみ |
| 0.0-0.3 | フックなし |

### 仮説検証率

| スコア | 基準 |
|--------|------|
| 0.9-1.0 | 全仮説が検証済み（validated/refuted） |
| 0.7-0.9 | 80%以上の仮説が検証済み |
| 0.5-0.7 | 50-80%の仮説が検証済み |
| 0.3-0.5 | 30-50%の仮説が検証済み |
| 0.0-0.3 | 30%未満の仮説が検証済み |

## エラーハンドリング

| 状況 | 対応 |
|------|------|
| 一次資料が見つからない | Level 2-3 から概要を構築、`primary_source` を欠損マーク |
| API レート制限 | 指数バックオフでリトライ、代替ソースへフォールバック |
| 矛盾する情報 | 両論併記、controversies に記録、信頼度の高いソースを優先表示 |
| トピックが曖昧 | 候補を列挙してユーザーに確認 |
| MECE ギャップ検出 | 優先度に応じて追加収集を実行 |
| フック不足 | Level 4（考察・民間知識）を重点的に追加収集 |
| 仮説が全て棄却 | 新たな仮説を設定し、収集プロセスを再実行 |
| エキスパートにアクセス不可 | 代替ソース（学術論文、インタビュー記事）で補完 |

## 使用例

### 入力

```
トピック: 桃太郎
```

### 出力（抜粋）

```yaml
topic: "桃太郎"
aliases: ["ももたろう", "Momotaro"]

hypothesis:
  initial_hypothesis:
    statement: "桃太郎は古代の政治的出来事（吉備国平定）を反映した民話である"
    rationale: "地名の一致、桃の呪術的意味、鬼の正体に関する諸説から推測"
    assumptions:
      - assumption: "成立時期と吉備国関連の歴史的事件が時期的に一致する"
        testable: true
      - assumption: "岡山（吉備国）との地名・伝承の対応がある"
        testable: true
  validation_tracking:
    - hypothesis: "吉備国平定説"
      status: partial
      evidence:
        - finding: "柳田國男が1933年に同様の説を提唱"
          source: "『桃太郎の誕生』"
          supports: true
        - finding: "成立時期（室町末期）と吉備国平定（古墳時代）に大きな時間差"
          source: "国文学研究資料館"
          supports: false
      confidence: 0.5

issue_tree:
  root_question: "桃太郎とは何か？その本質的意味は？"
  branches:
    - issue: "物語の原典と内容は？"
      type: what
      status: answered
      answer: "室町時代末期成立。御伽草子版が最古。複数のバリエーションあり"
      confidence: 0.85
    - issue: "なぜこの物語が生まれたか？"
      type: why
      status: in_progress
      sub_issues:
        - issue: "歴史的背景は？"
          status: partial
        - issue: "桃の象徴的意味は？"
          status: answered

prioritization:
  - item: "原典テキストの取得"
    impact: high
    effort: low
    availability: high
    score: 9.0
    action: collect_now
  - item: "エキスパートインタビュー"
    impact: high
    effort: high
    availability: medium
    score: 2.0
    action: collect_later

primary_source:
  full_text: "むかしむかし、あるところに、おじいさんとおばあさんが..."
  source: "青空文庫 - 楠山正雄『桃太郎』"
  source_url: "https://www.aozora.gr.jp/..."
  original_date: "室町時代末期（原型）"
  variants:
    - version_name: "御伽草子版"
      differences: "桃を食べて若返った老夫婦から生まれる"
      source: "国立国会図書館デジタル"

synthesis:
  so_what_chain:
    - finding: "桃太郎の最古の文献は室町時代末期"
      so_what_1: "500年以上の歴史がある"
      so_what_2: "日本人に長く愛されてきた普遍的な物語"
      so_what_3: "時代を超えて共感される普遍的要素がある"
      final_insight: "桃太郎には人間の根源的な願望（成長、正義、帰還）が含まれている"
  governing_thought: "桃太郎は、若者の成長と社会への貢献という普遍的テーマを、日本的な象徴（桃、鬼、きびだんご）で表現した民話である"
  scqa:
    situation: "桃太郎は日本で最も有名な昔話の一つであり、誰もが知っている"
    complication: "しかし、その起源・本来の意味・なぜ長く愛されるかは諸説あり不明確"
    question: "桃太郎の本質的な意味と、現代における価値は何か？"
    answer: "桃太郎は成長譚の原型であり、『弱者が仲間を得て強大な敵に立ち向かう』という普遍的構造が、時代を超えた共感を生んでいる"

knowledge_graph:
  nodes:
    - id: momotaro
      type: Person
      label: "桃太郎"
      properties:
        role: "主人公"
        origin: "桃から誕生"
    - id: oni
      type: Person
      label: "鬼"
      properties:
        role: "敵役"
        location: "鬼ヶ島"
    - id: onigashima
      type: Place
      label: "鬼ヶ島"
      properties:
        model: "女木島（香川県）説あり"
  edges:
    - from: momotaro
      to: oni
      relation: "contrasts_with"
      description: "善vs悪の対立構造"
    - from: oni
      to: onigashima
      relation: "located_in"

engagement:
  hooks:
    - type: mystery
      content: "なぜ『桃』から生まれたのか - 中国の桃信仰との関連"
      target_emotion: "知的好奇心"
      curiosity_score: 0.85
    - type: counterintuitive
      content: "芥川龍之介版では鬼が被害者として描かれる"
      target_emotion: "驚き"
      curiosity_score: 0.9
    - type: hidden_truth
      content: "原典（御伽草子版）では老夫婦が桃を食べて若返り、その後に生まれた"
      target_emotion: "発見"
      curiosity_score: 0.8
  tension_points:
    - topic: "桃太郎は正義か侵略者か"
      positions: ["伝統的解釈：鬼退治の英雄", "現代的再解釈：一方的な侵略者"]
      narrative_potential: "価値観の転換を促す議論ネタ"

mece_coverage:
  dimensions:
    temporal:
      past: 0.9
      present: 0.7
      future: 0.3
    perspective:
      protagonist: 0.9
      antagonist: 0.6
      observer: 0.5
  gaps:
    - dimension: "temporal"
      value: "future"
      priority: "low"
    - dimension: "perspective"
      value: "antagonist"
      priority: "medium"

metadata:
  collected_at: "2026-01-05T12:00:00Z"
  sources_used:
    - "青空文庫"
    - "Wikipedia"
    - "CiNii"
    - "国立国会図書館"
    - "『桃太郎の誕生』柳田國男"
  confidence_score: 0.82
  completeness_score: 0.75
  engagement_score: 0.85
  hypothesis_validation_rate: 0.6
```
