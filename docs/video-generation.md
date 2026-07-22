# Video Generation System

動画生成システム - 物語スクリプトから最終動画を生成する手順書

## 概要

このドキュメントは、`docs/story-creation.md` で生成した物語スクリプトを、生成AIを活用して動画に変換するための手順を定義する。

### 関連ドキュメント

- `docs/orchestration-and-ops.md`（全体制御・品質保証・配信/改善ループ）
- [`docs/implementation/video-prompting.md`](implementation/video-prompting.md)（動画設計から provider prompt への projection / compiler 契約）
- [`workflow/playbooks/video-generation/kling.md`](../workflow/playbooks/video-generation/kling.md)（Kling 固有の prompt policy）
- [`docs/data-contracts.md`](data-contracts.md)（manifest / materialized payload のデータ契約）

### 位置づけ

```
[情報収集] → [物語生成] → [動画生成]
                           ↑ 本書
```

### 入力

- `output/<topic>_<timestamp>/story.md` - 物語スクリプト
- `output/<topic>_<timestamp>/script.md` - scene / cut の意味と narration 正本
- `output/<topic>_<timestamp>/video_manifest.md` - scene / cut / provider 実行設計の正本

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

### 2.2.0 Scene-to-Clip 接続原則

動画生成では、scene/cut の canonical design と provider prompt を分離する。高品質な still があっても、motion が cut の役割を満たさなければ、clip は「絵が動いただけ」になりやすい。一方、`cut_function` や event ID をそのまま provider へ渡しても映像指示にはならない。

原則:

- p400 の `cut_contract` は、物語上の責務、event / reveal 境界、開始状態、主動作、終了状態、continuity を保持する正本である
- p800 は [`video prompt projection registry`](implementation/video-prompting.md) で必要情報を `start_state`, `primary_motion`, `camera_motion`, `environment_motion`, `emotional_change`, `end_state`, `continuity`, `constraints` へ分類する
- `compile_video_api_prompt_v1` が active fragment だけを自然文化し、provider 送信正本 `video_generation.api_prompt_payload.prompt` を生成する
- `cut_function`, `target_beat`, event / reveal ID は review 根拠として使い、provider prompt 本文へ出さない
- p600 still は action を完了させず、p800 motion が始まる余白を残す。
- `motion_brief` は p800 専用入力であり、p600 image prompt authoring では参照しない。p600 は `first_frame_brief` までを使い、動画開始後の動きは知らない前提で still を作る。
- p800 motion は p600 still に無い人物・重要道具・新しい reveal を勝手に追加しない。
- narration は motion の説明書ではない。映像で読めることを重複説明しすぎない。
- cut 数は duration の割り算から増やさない。原因、反応、可視証拠、許可済み location 遷移、deadline、終了状態など、互いに異なる semantic obligation を exactly once 被覆する最小数から決め、尺だけを埋める filler cut を作らない。
- first frame は開始境界、last frame は到達境界として扱い、単一の連続 shot の途中で fade / cut / 別 shot 化しない
- `video_metadata.time` と `scene.time_of_day` は動画中に描き直す指示ではなく、時代、衣装、建築、光、影、色温度を変えない continuity として投影する

#### Function / obligation 単位の具体化

同じ `location_segment` が複数の event beat または複数 cut を担う場合、scene 設計は完成 prompt を複製せず、次の3段階で差分を持つ。

```text
location_segments[].primary_subject_by_function
  -> beat_overrides.<setup|pressure|turn|payoff>
  -> obligation_overrides.<obligation_id>
  -> cut first-frame / motion contract
  -> provider prompt compiler
```

- `primary_subject_by_function` は beat function ごとの主被写体を確定する。未指定なら segment の `primary_subject` を継承する
- `beat_overrides.<function>` はその場所・function の canonical event beat を具体化する。同じ function の全 cut へ無条件に prompt prose を複写しない
- `obligation_overrides.<obligation_id>` は一つの cut 責務だけに適用する最も狭い差分であり、`location / primary_subject / visible_action / visible_reaction / required_visual_evidence / required_roles / visible_character_state / first_frame_character_asset_overrides / first_frame_excluded_object_ids / motion_brief / motion_end_state / motion_attention_target / environment_motion / emotional_change / retain_carried_character_subjects / allowed_new_reveal_elements / allowed_reveal_info_ids / use_next_cut_first_frame_as_last_frame` を必要なものだけ上書きする。`location` は exact `scene.location_sequence[]` 内に限る
- `retain_carried_character_subjects` は既定 `true`。`false` は前 cut から自動 carry された人物を今回の subject/reference set に残さない指定であり、current cut の `required_roles` や明示 evidence を落とす指定ではない
- 解決優先順位は `obligation override -> beat override -> function別subject / segment既定 -> scene既定`。空 map は継承であり、空文字による削除ではない

reveal / boundary の3 key は exact `obligation_id` entry だけに置き、同じ function の sibling cut へ広げない。

- `allowed_new_reveal_elements[]`: 開始画像にないが、この主動作で新しく現れてよい具体的な人物状態・小道具・舞台要素。最大8件、非空・一意、`motion_brief` または `motion_end_state` に明示し、`must_not_add` と交差させない
- `allowed_reveal_info_ids[]`: canonical reveal inventory のうち、この cut だけで解禁する情報 ID。source-event / narration review へ投影し、provider prose へは出さない
- `use_next_cut_first_frame_as_last_frame`: 次 cut が存在し、current end state と許可済み reveal が next first-frame contract の開始状態に exact match する場合だけ `true`。同一場所はその一致を必須とし、cross-location はさらに exact destination が `scene.location_sequence[]` と current obligation の `allowed_new_reveal_elements[]` の双方に存在する場合だけ許可する。current `last_frame` を次 cut の承認済み first-frame image に exact binding する

`use_next_cut_first_frame_as_last_frame` は allowlist の代用ではない。開始画像から新要素が現れるなら `allowed_new_reveal_elements`、新しい物語情報を開示するなら `allowed_reveal_info_ids` を同じ obligation で明示する。次 cut 不在、未承認 next frame、end/start state または reveal 差分の不一致、`scene.location_sequence[]` / allowlist に exact destination がない cross-location は materialization を拒否する。

画像側は action の完了や future motion を描かず、解決済みの主体、可視 action/reaction、evidence、role、character state から first frame を一枚だけ作る。動画側はその承認済み first frame から、解決済み `motion_brief` を一つの `primary_motion`、`motion_end_state` を `end_state`、`environment_motion` / `emotional_change` を対応する補助 fragment へ投影する。`motion_attention_target` は upstream cut authoring の判断補助であり、現行 compiler はこの field を独立 projection source / trace / provider fragment にしない。cut contract に保持された値は normalized design source として `source_digest` を変え得る。provider に必要な対象指向は登録済みの `motion_brief`、`emotional_change`、`end_state` に具体化する。

function 名、obligation ID、override map、未採用候補は review / digest に残してよいが provider prose へ出さない。location override は exact `scene.location_sequence[]` 内で cut の開始場所を選べる。解決後の cut は一つの出発 segment、一つの primary subject、一つの可視主動作に確定し、cross-location は上記の exact binding を満たす last-frame 到達境界だけを例外として許可する。sequence 外の場所、連続 motion 中への別場所混入、actor inversion、抽象 placeholder、未解決 alternative は materialization 前に拒否する。

video compiler は `allowed_new_reveal_elements` を positive prompt の `constraints` fragment に明示し、許可要素以外の新規追加を禁止する。separate negative channel では positive allowlist 文と許可要素名を `negative_prompt` に複写せず、「承認済み要素以外」の禁止だけを残す。Seedance の inline mode は保存 `negative_prompt` を空にし、allowlist と残余禁止を positive constraints に保持する。

canonical motion design の最小構造:

```yaml
cut_contract:
  first_frame_contract:
    visible_start_state: {}
    first_frame_brief: "<承認済み still で見える開始状態>"
  motion_contract:
    motion_brief: "<1 clip が担う一つの主動作>"
    motion_attention_target: "<upstream authoring用。現行video compilerの入力/traceではない>"
    camera_motion: "<主動作と競合しない camera。Kling は最大2指示>"
    environment_motion: "<開始画面に存在する小さな環境変化>"
    emotional_change: "<表情・姿勢・視線で読める変化>"
    end_state: "<可視終了状態または handoff>"
    allowed_new_reveal_elements: []
    must_not_add: []
  continuity_contract:
    carry_forward_to_next_cut: []
  source_event_contract:
    allowed_reveal_info_ids: []
  cut_handoff:
    delivers_to_next:
      binds_video_last_frame_to_next_first_frame: false

video_generation:
  first_frame: "<current cut approved first-frame image>"
  last_frame: ""  # boundary=true のときだけ next cut approved first-frame image
```

frontend/server、CLI、scene storyboard のどの経路でも、生成前に compiler output と hash を manifest / review artifact へ materialize する。materialize は approval ではない。生成 API は保存済み `prompt` / `negative_prompt` / `sha256` / `source_digest` / `provider_request_binding` と per-item approval identity を照合し、未 materialize、pending、または stale な request を拒否する。

### 2.2.1 Human Review Change-Request Loop

人間レビューは `approved|changes_requested` の二値だけで終わらせない。

- `changes_requested` になったら、正本 artifact 側の `human_review.change_requests[]` に要求を分解して残す
- `human_review_ok` は evaluator finding の例外許容であり、通常の修正要求フローとは分ける
- narration の正本は `script.md`
- image / manifest / video の review feedback は `video_manifest.md` または stage artifact に残す

最小 contract:

```yaml
human_review:
  status: "pending|approved|changes_requested"
  notes: ""
  change_requests:
    - request_id: "hr-001"
      status: "open|accepted|rejected|deferred|resolved"
      category: "story_alignment|reveal|continuity|timing|audio|other"
      requested_change: ""
      rationale: ""
      requested_at: "ISO8601"
      resolved_at: ""
      resolution_notes: ""
```

動画 cut の採否ルール:

- `scene/cut` を動画化しない判断は、人レビューに基づく `delete_scene` / `delete_cut` だけで行う
- `reuse_anchor` / `no_dedicated_still` / `motion chain` は image planning の圧縮表現であり、動画 cut の採否理由として使わない
- 人レビューで削除されていない story cut は、既定で `video_generation` を持つ
- つまり `image_generation` と `audio` が残っているのに `video_generation` だけ自動で落とす、という設計は採らない
- ただし scene に `render_units[]` がある場合、最終 render の動画クリップ単位は render unit で表す
  - cut は story / image / audio の正本のまま残す
  - render unit は `source_cut_ids[]` で複数 cut の narration を 1 本の動画に束ねられる
  - `source_cut_ids[]` は canonical cut 順を保ち、active cut を scene 内で exactly once 被覆する。重複・欠落・deleted cut 参照は禁止する
  - unit duration は source cut duration の合計と一致させ、選択した provider / model / input mode の capability 上限を超える場合は unit を分割する
  - 1 cut unit は source contract を exact 継承する。explicit unit contract は field を省略でき、空値は no-op として扱う。非空の指定値は対応する source value と一致しなければならない（非空 allowlist は normalized member set で比較する）。異なる値を拒否し、出力は常に source contract そのものとする
  - 複数 cut unit は先頭の first-frame 境界、末尾の end-state、全 cut の continuity / prohibition を effective contract とし、個別 cut の主動作は連結しない。explicit reveal allowlist は source cut 順に stable dedupe した reveal union と normalized member set が exact 一致しなければならず、出力順は stable source order に正規化する。欠落も superset による新 reveal の発明も拒否する。source union が非空なら explicit allowlist を必須、空なら absent または空にする
  - 複数 cut unit の一つの primary motion は unit-level `cut_contract.motion_contract` または `prompt_authoring_source` に明示する

### 2.2.2 Script と Manifest の参照優先順位

画像生成と動画生成では、`script.md` と `video_manifest.md` の役割を分けて読む。

- `script.md`
  - 意味の参照元
  - 物語進行、`visual_beat`、reveal、human review の意図を持つ
- `video_manifest.md`
  - 実装の参照元
  - prompt、asset、reference、motion、continuity を持つ

既定の読み順:

1. `video_manifest.md` の canonical `cut_contract` と first / last frame、provider 設定を読む
2. 必要な意味境界を `script.md` で確認する
3. registry / compiler で `video_generation.api_prompt_payload` を materialize する
4. review 後の provider 実行は保存済み `api_prompt_payload.prompt` だけを読む
5. narration は補助参照に留め、provider motion prompt へ複製しない

重要:

- `audio.narration.tts_text` は TTS 専用字段であり、image/video generation の主ソースにしない
- image/video prompt は `tts_text` を基準に組み立てない
- human review がナレーション review 段階で image/video まで踏み込んだ場合は、`script.md.human_change_requests[]` と `approved_image_notes[]` / `approved_video_notes[]` を参照し、その内容が `video_manifest.md` に materialize されていることを前提に生成へ進む

### 2.2.3 画像生成は 2 段に分ける

画像生成は次の 2 段で扱う。

1. asset stage
   - `asset_plan.md` を作る
   - human review を通す
   - reusable asset を生成する
   - `reference_count == 0` の image request だけは bootstrap lane を使ってよい
   - provider 実行前に `asset_generation_requests.md` を materialize して review できる
   - rerun で比較案が必要なときだけ `--force --test-image-variants N` で `assets/test/` に追加候補を出す
2. cut stage
   - 既存どおり `video_manifest.md` を使って各 cut 画像を生成する
   - provider 実行前に `image_generation_requests.md` / `video_generation_requests.md` を materialize して review できる

stage 1 の原則:

- `asset_plan.md` は asset 設計の正本
- 作成時に `script.md` の該当箇所を必ず参照する
- character は従来どおり複数 view 運用を維持する
- object / location / setpiece / reusable still は単体 anchor still を基本にする
- asset を作る主目的は、複数 cut で使う visual identity を固定し、同一 cut 内でも関連 asset を派生させながら物語の視覚表現をブレさせないこと
- 人間レビューで通るまで asset 生成に進まない
- asset stage 完了時は、次が human review 待ちであることを明示してユーザーへ確認を促す
- 浦島 run のように scene still を後から asset に昇格する例外はあるが、それは設計移行中の互換運用であり、今後の標準フローでは asset stage を先に置く
- Codex built-in image generation（現行想定モデル: `gpt-image-2`）を repo の標準画像基盤にする
- 外部課金系の画像 provider は標準ワークフローでは使わない
- request file は「最終的にこの prompt / reference / output で投げる」を確認するための凍結成果物として扱う
- `plan` は設計用、`request` は人レビュー用と割り切る
- 人が review する既定の対象は request file
- `image_generation_requests.md` / `video_generation_requests.md` では、必要に応じて `source_requests` metadata を併記し、どの `human_change_requests[]` がこの request に反映されたか読めるようにする
- request 本文では、参照画像に写っている人物/場所/小道具が、この場面でどう使われるかを書く
- `後続sceneでも一致させる` のような、参照画像を伴わない stateful 前提の文は request としては弱い
- request 本文では `cut` のような運用メタ語を使わない
- request 本文では `assets/...png` のような path を直接書かない
  - `人物参照画像1`, `場所参照画像1`, `小道具参照画像1` のような役割付きラベルを使う
  - 実 path は metadata の `references` に残す
- request 本文では `物語「<topic>」の sceneXX` や `この画像は物語「<topic>」の一場面` のような制作メタ情報を使わない
- 作品文脈が必要な場合も、人物 / 場所 / 道具 / 行為を具体語で書く。例: `シンデレラの灰の台所`、`王宮の階段に残された片方のガラスの靴`
- scene image request の本文生成では、`script.md` の `human_review.approved_visual_beat` を最優先し、なければ `visual_beat` を使う
- `story.md` は背景参照には使えても、scene image request の場面定義では `script.md` に優先されない
- scene image request を全面改稿する場合は、scene 単位で request authoring subagent を並列起動してよい
  - 各 subagent の入力は `script.md` / `video_manifest.md` / 現在の `image_generation_requests.md` / `docs/implementation/image-prompting.md`
  - motion や first/last frame の判断が絡む scene では `docs/video-generation.md` も入力に含める
  - 出力は scene 単位 scratch rewrite
  - 統合は担当 `p600` L2 supervisor が行い、最終的な `image_generation_requests.md` を凍結成果物にする
  - subagent は生成候補、clip review、除外理由の下書きまでを担当し、採用判定と `video_manifest.md` 更新は担当 bucket の L2 supervisor が行う
  - 採用した subagent output は `subagent_trace` または `logs/review/` に残し、親会話だけにある判断を正本にしない
- scene image prompt は、カット全体の出来事をそのまま描くのではなく、**その動画を始める最初の1フレーム**として妥当である必要がある
- still は `cut_blueprint.cut_function` に対応して設計する。setup cut と turn cut では、同じ場所でも構図・距離・光の役割が違う
- p600 image prompt authoring は `first_frame_brief` を使い、`motion_brief` は読まない
- `first_frame_brief` と `motion_brief` が矛盾する場合は、p800 へ進まず p400 の cut blueprint 設計へ戻す。p600 still prompt に `motion_brief` を混ぜて解決しない
- `Aが話し、Bがうなずく` のような表現は、動画側で始まるべき動きを still 側で完了させやすいため避ける
- 推奨は、抽象的に `動き出す直前` と書くのではなく、その場面の動きに応じて `まだ口を開く前`, `まだうなずき始めていない`, `差し出す直前`, `一歩目の体重移動の直前` のように具体化すること
- `最初の1フレーム` / `1フレーム目` / `first frame` という制作メタ情報そのものは request 本文に入れない。これは p600 authoring / review の前提であり、画像生成 API に渡す意味がない
- ただしこの具体化は request generator のコードで自動変換しない。`script.md` と人レビューを読んだ自然言語エージェントが request を整え、evaluator がその妥当性を検査する

stage 2 の原則:

- 今までどおり `video_manifest.md` ベース
- canonical cut design は provider prompt と分離し、`api_prompt_payload` へ一方向 compile する
- `video_generation_requests.md` は exact compiled prompt と policy / compiler / source digest / prompt hash / settings を見せる review projection とする
- provider 実行は review Markdown を再解釈せず、保存済み payload と current design / settings の一致を gate にする
- cut stage 側でも human review が gate の場合は、次にどのレビューが必要かを完了報告に含める

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

#### Projection / compiler を正規入口にする

provider prompt を手書きの固定ブロックとして管理しない。canonical design を [`toc/video_prompt_projection_registry.py`](../toc/video_prompt_projection_registry.py) で分類し、`compile_video_api_prompt_v1` で active fragment だけを compile する。

```text
cut_contract + frames + temporal continuity + provider settings
  -> projection registry
  -> video_prompt_ir / projection_review_contract
  -> api_prompt_payload.prompt
```

`api_prompt_payload.prompt` は exact provider-facing text、`sha256` はその文字列の hash、`source_digest` は canonical design と exact negative prompt、duration / quality / aspect ratio、first / last / ordered references、provider model / execution options を含む compilation source の hash である。materializer が読める参照画像は file bytes hash も `provider_request_binding.execution_options.reference_content_sha256` に含める。prompt hash が同じでも review-only の event 境界や provider request が変われば source digest は変わり得る。

projection registry v5 は `must_not_surface / review_only` source の exact value を `projection_review_contract.review_only_sources[]` に残す。daypart visual basis、scene route / segments、cut responsibility、event / reveal 境界、scene 全体の `visualizable_action`、image / narration prose、reference path は semantic reviewer と `source_digest` には含めるが、provider prompt 本文へは出さない。caller の `review_only_dependencies` は string trim と空 descendant 除去後に非空なら exact normalized mapping を `projection_review_contract.review_only_dependencies` に返して digest に束縛するが、`prompt`、`negative_prompt`、top-level / IR の `included_fragments`、その他の IR fragment へは投影しない。未指定または正規化後に空なら field は出さない。

自由文 fallback を parse したかどうかと group 別の正規化結果は `projection_review_contract.authoring_source_normalization` に保存する。`video_prompt_ir.dependencies.has_references` は ordered video references の有無を必ず保持する。

identity は、編集可能な canonical design / `prompt_authoring_source`（authoring）、compiler version + `source_digest`（compiler）、保存済み prompt / negative prompt / `provider_request_binding`（persisted provider request）に分ける。`motion_prompt` を保存済み prompt から authoring input へ逆流させない。

frontend/server、CLI、scene storyboard は同じ compiler output を manifest と `video_generation_requests.md` へ保存する。materialize 直後は item ごとに `pending` である。frontend/server approval workflow は current semantic review 後の明示的な `approve_for_generation` でだけ approval を保存し、CLI の materialize-only / 通常実行は未承認 item を自動承認しない。CLI / server の実行は `status=approved` と `request_section_sha256` / `prompt_sha256` / `source_digest` の exact binding を必須にする。`prompt_sha256` は `api_prompt_payload.sha256` と同じ exact prompt hash である。`approved_by` / `approved_at` は監査情報であり request identity ではない。

provider adapter が表現できない承認済み入力を黙って捨てない。現在の Kling adapter は first / last frame のみを画像入力として扱い、auxiliary `references[]` は拒否する。Seedance の frame-boundary mode と multimodal-reference mode も混在させない。複数画像が必要な scene storyboard は、先頭 cut の full-frame image と storyboard を ordered references とする `reference_to_video` requestへ materializeし、reference対応modelを選ぶ。

payload `mode` は `text_to_video | image_to_video | first_last_frame | reference_to_video`。`provider_policy.multimodal_reference` と `provider_policy.negative_prompt_mode` は常に materialize し、`provider_request_binding.reference_roles` と `execution_options.extra_payload` はそれぞれ非空の ordered references / provider options がある場合だけ出す。

storyboard render unit の `video_input_contract.reference_roles[]` は `required_references[]` と同数・同順に保つ。`image_index` は1起点の連番・一意とし、image 1 を `start_state_visual_anchor`、image 2 を `ordered_storyboard_sequence_guide` に束縛する。この配列は compiler、`provider_request_binding.reference_roles`、IR、`source_digest`、server/CLI execution まで保持・照合し、provider prose には role 指示だけを出して path / ID / hash を出さない。

画像promptの `image_generation.references[]` は first frameを作るための入力に限定する。動画providerへ渡す参照は `video_generation.references[]` の明示値だけであり、両者を暗黙に混ぜない。

duration / reference count はprovider・model・input mode別capabilityで検査する。Seedance 1.0 reference-image modeは2–12秒、1–4参照であり、storyboard groupingからprovider dispatchまで同一上限を使う。

review artifact は positive prompt を `video_prompt` fence、negative prompt を `negative_prompt` fence に exact 保存する。section metadata の `prompt_sha256`（`api_prompt_payload.sha256` と同値）、`negative_prompt_sha256`、heading・metadata・両 fence を含む `request_section_sha256` を照合する。

compiler v5 の `quality_issues[]` に `blocking: true` が一件でもあれば、semantic review / approval / provider execution を止める。対象 code は `video_motion_generated_fallback`、`video_motion_unresolved_alternative`、`video_motion_abstract_primary`、`video_motion_abstract_end_state`、`video_motion_duplicate_environment`、`video_motion_duplicate_emotion`、`video_motion_sequential_overview`。compiled prompt を直接直さず、canonical motion field を具体化して再 materialize する。

#### プロンプト設計のDo/Don't

| Do | Don't |
|----|-------|
| canonical `motion_contract` に一つの主動作を書く | 自由文へ複数 event を連結する |
| first frame の可視状態から動かす | 参照にない人物・重要物・reveal を追加する |
| camera を主動作と両立させる | camera 指示を連続切替する |
| end state / last frame を到達境界にする | fade / cut で別 shot へ逃がす |
| continuity と高リスク制約だけを投影する | story key、ID、path、narration を本文へ出す |
| 上流設計を修正して再 materialize する | compiled prompt だけを直接修正する |

詳細な registry、8 groups、3 axes、payload / stale gate は [`docs/implementation/video-prompting.md`](implementation/video-prompting.md) を正本とする。

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

注意:
- 上の `-c copy` 結合は、入力 clip の video/audio stream 仕様が完全に同一の場合だけ使う
- 最終成果物の scene compile 結合では、事前に全 scene を正規化する
- 特に audio の `mono` / `stereo` 混在は禁止。`scene08: mono -> scene09: stereo` のような境界で、境界以降の音声がジャミング音・ノイズ化することがある

最終結合前の標準正規化:

```bash
ffmpeg -i sceneXX_compiled.mp4 \
  -vf "scale=1280:720,fps=24" \
  -af "aresample=44100,aformat=channel_layouts=stereo" \
  -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
  -c:a aac -b:a 192k \
  sceneXX_normalized.mp4
```

最終 `filelist.txt` には `sceneXX_normalized.mp4` だけを入れる。

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
   ├→ video prompt payload / review request の materialize
   ├→ hash・design digest・provider設定を照合して Image-to-Video変換
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
  - cut / render unit の canonical design を compile
  - api_prompt_payload と video_generation_requests.md を materialize
  - target ごとの exact request section / prompt hash / source digest を明示的に承認
  - review 済み payload の negative prompt / settings / frames / references / provider execution options まで照合して動画クリップ化

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
  time: "<story / script metadata からの歴史的時代 projection>"
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
    time_of_day: "夜明け"
    timestamp: "00:00-00:10"

    image_generation:
      tool: "codex_builtin_image"
      prompt: "string"
      output: "assets/scenes/scene1_base.png"
      iterations: 5
      selected: 3

    video_generation:
      tool: "kling_3_0 | kling_3_0_omni | seedance"
      input_image: "assets/scenes/scene1_base.png"
      prompt_authoring_source: "<frontend / legacy free-text fallback。canonical cut_contract が優先>"
      motion_prompt: "<api_prompt_payload.prompt の read-only compatibility projection>"
      api_prompt_payload:
        policy_version: "video_api_prompt_v1"
        compiler_version: "conditional_video_prompt_compiler_v5"
        projection_registry_version: "video_prompt_projection_registry_v5"
        provider: "kling_3_0"
        mode: "image_to_video"
        provider_policy:
          one_clip_one_intent: true
          max_camera_instructions: 2
          single_continuous_shot: true
          first_last_frame_boundary: false
          multimodal_reference: false
          negative_prompt_mode: "separate"
        provider_request_binding:
          duration_seconds: 10
          quality: "1080p"
          aspect_ratio: "16:9"
          first_frame: "assets/scenes/scene1_base.png"
          last_frame: ""
          references: []
          # reference_roles は references が非空の場合だけ同じ長さで materialize する
          execution_options:
            backend: "kling"
            model: "kling-3.0"
            # extra_payload は非空の場合だけ materialize する
            reference_content_sha256:
              assets/scenes/scene1_base.png: "<sha256-of-reference-bytes>"
        prompt: "<exact provider-facing motion prompt>"
        negative_prompt: "<exact compiled high-risk constraints>"
        source_digest: "<sha256-of-normalized-compilation-source>"
        sha256: "<sha256-of-exact-prompt>"
        quality_issues: []
        included_fragments: &scene_video_prompt_fragments
          - group: "start_state"
            text: "<compiled start-state fragment>"
          - group: "primary_motion"
            text: "<compiled primary-motion fragment>"
          - group: "continuity"
            text: "<compiled continuity fragment>"
          - group: "constraints"
            text: "<compiled constraints fragment>"
        omitted_groups: ["camera_motion", "environment_motion", "emotional_change", "end_state"]
        video_prompt_ir:
          schema_version: "video_prompt_ir_v2"
          provider: "kling_3_0"
          mode: "image_to_video"
          dependencies:
            story_time: ""
            time_of_day: "夜明け"
            has_first_frame: true
            has_last_frame: false
            has_references: false
            duration_seconds: 10
            reference_roles: []
            required_groups: ["start_state", "primary_motion", "continuity", "constraints"]
          included_fragments: *scene_video_prompt_fragments
          omitted_groups: ["camera_motion", "environment_motion", "emotional_change", "end_state"]
          quality_issues: []
        projection_review_contract:
          registry_version: "video_prompt_projection_registry_v5"
          group_order: ["start_state", "primary_motion", "camera_motion", "environment_motion", "emotional_change", "end_state", "continuity", "constraints"]
          authoring_source_normalization:
            applied: true
            groups:
              primary_motion: ["<normalized fallback candidate>"]
          groups: {}
          active_rules: []
          inactive_rules: []
          excluded: []
          review_only_sources: []
          shadowed_sources: []
          provider: "kling_3_0"
          mode: "image_to_video"
      output: "assets/scenes/scene1_video.mp4"

  - scene_id: 2
    time_of_day: "夜明け"
    timestamp: "00:10-00:20"
    # render-unit例が参照する最小source cut宣言。production cutはimage/audio等の完全契約も持つ。
    cuts:
      - cut_id: 1
        cut_contract:
          motion_contract:
            motion_brief: "<unit内のdistinct cause/evidence obligationを担うcut 1動作>"
            end_state: "<cut 1の可視終了状態>"
        video_generation:
          duration_seconds: 5
      - cut_id: 2
        cut_contract:
          motion_contract:
            motion_brief: "<unit内のdistinct reaction/payoff obligationを担うcut 2動作>"
            end_state: "<cut 2の可視終了状態>"
        video_generation:
          duration_seconds: 5

    # optional: cuts[] がある scene でだけ使う。存在時は最終 video clip の正本。
    render_units:
      - unit_id: 1
        source_cut_ids: [1, 2]
        # compiler が先頭/末尾境界と全 source cut の continuity を合成し、
        # explicit unit contract を同 group の優先値として重ねる。
        # allowed_new_reveal_elementsだけはsource reveal unionとのexact一致が必須で、supersetを拒否する。
        cut_contract:
          motion_contract:
            motion_brief: "<unit 全体を代表する一つの primary motion>"
        video_generation:
          tool: "kling_3_0"
          duration_seconds: 10
          first_frame: "<first source cut start frame>"
          last_frame: "<approved unit arrival frame>"
          references: []
          prompt_authoring_source: "<unit-level fallback; individual cut actionsを連結しない>"
          api_prompt_payload:
            policy_version: "video_api_prompt_v1"
            compiler_version: "conditional_video_prompt_compiler_v5"
            projection_registry_version: "video_prompt_projection_registry_v5"
            provider: "kling_3_0"
            mode: "first_last_frame"
            provider_policy:
              one_clip_one_intent: true
              max_camera_instructions: 2
              single_continuous_shot: true
              first_last_frame_boundary: true
              multimodal_reference: false
              negative_prompt_mode: "separate"
            provider_request_binding:
              duration_seconds: 10
              quality: "1080p"
              aspect_ratio: "16:9"
              first_frame: "<first source cut start frame>"
              last_frame: "<approved unit arrival frame>"
              references: []
              execution_options:
                backend: "kling"
                model: "kling-3.0"
                reference_content_sha256:
                  "<first source cut start frame>": "<sha256-of-reference-bytes>"
                  "<approved unit arrival frame>": "<sha256-of-reference-bytes>"
            prompt: "<exact compiled unit motion prompt>"
            negative_prompt: "<exact compiled high-risk constraints>"
            source_digest: "<includes ordered source_cut_ids and source contracts>"
            sha256: "<sha256-of-exact-prompt>"
            quality_issues: []
            included_fragments: &render_unit_video_prompt_fragments
              - group: "start_state"
                text: "<compiled unit start-state fragment>"
              - group: "primary_motion"
                text: "<compiled unit primary-motion fragment>"
              - group: "end_state"
                text: "<compiled unit end-state fragment>"
              - group: "continuity"
                text: "<compiled unit continuity fragment>"
              - group: "constraints"
                text: "<compiled unit constraints fragment>"
            omitted_groups: ["camera_motion", "environment_motion", "emotional_change"]
            projection_review_contract:
              registry_version: "video_prompt_projection_registry_v5"
              group_order: ["start_state", "primary_motion", "camera_motion", "environment_motion", "emotional_change", "end_state", "continuity", "constraints"]
              groups: {}
              active_rules: []
              inactive_rules: []
              excluded: []
              review_only_sources: []
              # exact normalized review metadata only。provider / IR fragment へ複写しない
              review_only_dependencies:
                render_unit_source_cut_ids: ["1", "2"]
                render_unit_source_cut_contracts:
                  - motion_contract:
                      motion_brief: "<unit内のdistinct cause/evidence obligationを担うcut 1動作>"
                      end_state: "<cut 1の可視終了状態>"
                  - motion_contract:
                      motion_brief: "<unit内のdistinct reaction/payoff obligationを担うcut 2動作>"
                      end_state: "<cut 2の可視終了状態>"
              shadowed_sources:
                - source_key: "compiler_normalized.authoring_source.primary_motion"
                  target_group: "primary_motion"
                  reason: "higher_priority_design_source_present"
              provider: "kling_3_0"
              mode: "first_last_frame"
              authoring_source_normalization:
                applied: true
                groups:
                  primary_motion: ["<normalized unit fallback candidate>"]
            video_prompt_ir:
              schema_version: "video_prompt_ir_v2"
              provider: "kling_3_0"
              mode: "first_last_frame"
              dependencies:
                story_time: ""
                time_of_day: "夜明け"
                has_first_frame: true
                has_last_frame: true
                has_references: false
                duration_seconds: 10
                reference_roles: []
                required_groups: ["start_state", "primary_motion", "end_state", "continuity", "constraints"]
              included_fragments: *render_unit_video_prompt_fragments
              omitted_groups: ["camera_motion", "environment_motion", "emotional_change"]
              quality_issues: []
          output: "assets/scenes/scene2_unit1.mp4"

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

`scripts/build-clip-lists.py` は `*_generation_exclusions.md` も出力する。`cut_status: deleted` の cut は動画・ナレーションの concat list に入らない。

## Human Change Request Expansion

script review で image / video まで踏み込む修正要求が来る前提では、`script.md` の `human_change_requests[]` を正本にし、`video_manifest.md` には実行用の trace を materialize する。

- `assets.location_bible[]`
  - 場所の再利用 anchor
- `still_assets[]`
  - 1 cut で複数 still を作る canonical field
- `reference_usage[]`
  - 背景として見せる、同カメラで派生する、状態遷移に使う、を明示する
- `implementation_trace`
  - どの人レビュー request を反映したかを node ごとに残す

generation 前 gate は次を止める。

- unresolved `human_change_requests[]`
- `applied_request_ids[]` 欠落
- `still_assets[]` の dependency 未解決
- `reference_usage` の target asset 不在
