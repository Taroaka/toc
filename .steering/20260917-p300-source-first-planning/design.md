# p300：原作を保持する映像設計

状態: 設計提案。稼働中の正本契約は未変更。
対応要件: [requirements.md](requirements.md)。実装順: [tasks.md](tasks.md)。

## 1. p300の仕事

「この物語を映像にするとき、何を保ち、どこに見せ方の判断が必要か」を考える。
判断が必要な箇所だけ、具体的な演出と一貫性の指定を残す。

```text
research + story + ユーザーの映像方針
                 ↓ 本文を直接読む
           p310: 必要な映像設計
                 ↓ 構造・参照検証
           p330: 引き継ぎを確定
                 ↓
story本文 + visual_value.md → p400のscene/cut設計
                 └────────→ p500〜p700の素材・画像・語り
```

単に問題を修復する工程にはしない。作品に合った大胆な映像や静かな映像も設計できる。
一方、設計書を埋めるための追加scene・象徴・反復・演技を要求しない。

## 2. 現行の原因と変更箇所

| 確認箇所 | 現行の問題 | 設計上の変更 |
| --- | --- | --- |
| `scripts/toc-immersive-frontend-run.py::_adaptation_intent_for_profile` | 原作の意味を尊厳・選択・証明に固定 | 新規p300経路から除外。原作本文とユーザー方針からauthorが記述 |
| 同 `::_scene_value_amplification_for_profile` | 定型の感情・演出。value参照をシーン位置で選ぶ | v2では呼ばない。具体的な追加判断のみ執筆 |
| 同 `visual = {...}` | 配色・アンカー・再利用画像・handoff文を固定 | 共通authoring入口の出力を検証して採用 |
| `toc/adaptation_value_contract.py` | 相反感情・象徴的瞬間・演出5領域等を全sceneで必須化 | v1互換とv2のsource保持を分離 |
| 同 `::_visual_projection_issues` | p300のamplification全文一致をp400に要求 | v2はsource digest、scene対応、受領したメモの保存を照合 |
| frontendのscene intent / expressive contract / source ledger | 旧欄を直接参照・複製し、cutでも定型文に展開 | v2の疎なメモと原作参照を渡す。旧欄の穴埋めをしない |
| `toc/stage_evaluation/research_story.py` | scene配列が空ならcoverage検証を抜ける経路がある | v2では全sceneが必要。各sceneのnotesだけ空を許可 |

`scene10_cut01` の10は既存runtimeの番号体系では先頭sceneを指すことがある。
「10番目のsceneが必ず必要」という問題ではなく、作品に応じたアンカー判断をしていない点が問題。

## 3. 判断の進め方

1. ユーザー指定、research、storyの本文・全scene・出典を読む。
2. 既にstoryにある出来事、意味、開示順、曖昧さ、creative additionをそのまま扱う。
3. 全編で共有する画作りの判断があれば記す。未指定部分を固定の配色や象徴で埋めない。
4. 各sceneについて、映像化で伝わらなくなること、見せると早すぎること、
   この作品で活かしたい表現があるかを考える。必要な判断だけnotesへ書く。
5. 複数sceneに出る人物・物・場所・状態の認識を保つ必要があれば、一貫性のメモを記す。
6. ID・source・形式を検証して、成果物とstateを確定する。

手順3〜5の問いは執筆の手掛かりである。回答欄・チェック済みフラグ・点数に変換しない。
全sceneで「問題・原因・解決策」の3欄を必須にする代案も採用しない。

## 4. 成果物の最小構造

成果物名は `visual_value.md` を維持。新規契約名は
`visual_value_metadata.visual_planning_contract: source_first_v2` とする。
現行のv1 adaptation契約とは別の版識別子として明示的にdispatchする。

### 4.1 必須の外枠

| フィールド | 書く担当 | 意味 |
| --- | --- | --- |
| `visual_value_metadata.visual_planning_contract` | 実行コード | 新旧形式の識別 |
| `visual_value_metadata.source_bindings` | 実行コード | research/storyのrun内相対パスと読込時bytesのSHA-256 |
| `scene_visual_values[].scene_selector` | author、コードで照合 | storyに実在するscene ID。全sceneをstory順に一度ずつ出力 |
| `scene_visual_values[].notes` | author | 必要な判断の文章配列。`[]`が正常な値 |

入力digestはauthorに作らせない。source_bindingsを通して、上流のvalue ID・event ID・
reveal契約を本文ごと参照できる。短縮profileだけを保存して本文を切り離さない。
全sceneの行はauthorが返す。コードが欠けたsceneをnotes空で補完してはならない。

### 4.2 任意の内容

| フィールド | 書く内容 | 空・未指定の扱い |
| --- | --- | --- |
| `global_visual_identity.notes` | 全編で共有する作品固有・ユーザー指定の見せ方 | block省略可、notesは空でも可 |
| `continuity_notes[]` | source参照、対象scene、保持する見た目・状態・位置関係 | 配列省略または空が正常 |

continuityの一項目は `source_refs`、`scene_selectors`、`note` を持つ。
source_refsは既存source bindingの名前とJSON Pointerを使い、参照先を構造検証できるようにする。
参照先はresearch/storyの人物・物・場所・具体的な状態。対応IDがなければscene内の該当記述を参照する。
将来のasset IDやcut IDを発明しない。

元のasset candidates、anchor candidates、reference strategy、regeneration risks、stage別handoffは、
v2では別々の必須blockにしない。同じ「何を保ち、なぜ参照が必要か」を繰り返さず、
continuity_notesまたは該当sceneのnotesに一度だけ書く。p500が必要な参照画像・viewを具体化する。

演出分野別の固定キーを設けない。演技・空間・構図・音・編集は必要に応じて一つの文章で扱える。
notesの役割は見せ方の判断であり、storyの事実を改訂することではない。

### 4.3 書式例

下記は架空の入力を想定した説明例。実行用fixtureではなく、ID・文章・hashをテンプレートの
標準値にしてはならない。参照先に該当する入力がある場合にのみ成立する。

```yaml
visual_value_metadata:
  visual_planning_contract: source_first_v2
  source_bindings:
    research: {path: research.md, sha256: "<実行コードが計算するSHA-256>"}
    story: {path: story.md, sha256: "<実行コードが計算するSHA-256>"}

scene_visual_values:
  - scene_selector: scene_meal
    notes: []
  - scene_selector: scene_recognition
    notes:
      - "人物が器の欠けに気づく場面なので、前の食事場面と同じ欠けだと見分けられる大きさで見せる。気づく前に欠けだけを強調しない。"

continuity_notes:
  - source_refs:
      - {source: story, pointer: /script/scenes/0}
      - {source: story, pointer: /script/scenes/1}
    scene_selectors: [scene_meal, scene_recognition]
    note: "両場面で同じ器を使う。欠けの形と位置を保つ。"
```

最初のsceneに「平穏から不穏へ」などを足す必要はない。
また、広大な場所への初到着を見せる原作なら、人物と場所のスケールを同時に読める見せ方を
積極的に提案できる。壮観をなくす設計ではない。
語りが必要な原作では、情報を画だけに押し込めず、語りとの分担をnotesに書ける。

## 5. authoring実装

共通の `toc/visual_value_authoring.py` と薄いCLI
`scripts/author-visual-value-with-codex.py` を新設する案とする。
既存 `toc/story_author_runtime.py` / `server/codex_app_server.py` のtransport・診断・
記録を再利用し、frontendはstory執筆後に共通入口を呼ぶ。

- `prepare-stage-context.py --stage visual_value` のreadsetと入力本文を渡す。
- 一回の全編authoringで前後関係を読めるようにする。subagent、critic、候補の採点は追加しない。
- 上流本文を欠落させる黙示的なtruncateをしない。入力が収まらない場合は入力制約として報告する。
- source bindingとscene対応を検証し、既存run lock・安全なatomic write・append-only stateを使う。
- parse/sourceエラーはownerが修正可能。再試行上限は既存runtimeに従い、失敗を定型文で埋めない。
- 上流を読んだsource hashとcommit直前のsource hashが異なればstaleとして再実行する。
- authorが明示した全sceneのnotes空は成功。transport failure、途中応答、欠けたsceneは失敗。
- `scripts/toc-run.py` / `scripts/toc-immersive-ride.py` のscaffoldは新形式を案内するが、
  templateを作っただけでp310 doneにしない。assistantの直接執筆も同じvalidatorを使う。

LLMを呼ぶだけでは具体性は保証されない。本文を直接渡すこと、固定fallbackを除くこと、
欄埋めを要求しないことをセットで変更する。

## 6. 後工程への引き継ぎ

| 工程 | 必須の入力と責任 |
| --- | --- |
| p400 | story本文とp300全体を直接読む。sceneのnotesを受け取り、具体的なevent/cutへ落とす。cutの数や順序はここで決める |
| p500 | story/scriptの対象とcontinuity_notesを読み、必要な素材・参照・viewを設計する。存在しない象徴物を補完しない |
| p600 | script、素材のbindings、関連notesから描画可能な状態を組み立てる。抽象的な設計文をprovider promptへ直結しない |
| p700 | story/scriptと関連notesから語りの分担を保つ。全scene無言を要求しない |

v2のscript/manifestは、それぞれ既存metadata内に同じ `visual_planning_contract` と
`source_visual_value: {path, sha256}` を持つ。
各sceneは `source_story_scene_id` を持ち、runtimeの10/20等の番号と上流IDを明示対応させる。
`scene_intent.visual_notes` はp300のnotesを受領情報としてそのまま保存する。
具体化した演出は既存scene/event/cutのauthoring領域に書く。

全文保存の対象は疎な受領メモだけである。旧 `scene_value_amplification` の多数の欄を
再作成したり、その構造へ変換したりしない。受領情報の保存が、演出内容の実現を証明するとは扱わない。
global/continuityの正本はsource_visual_valueで参照し、多重に編集可能なコピーを増やさない。

v2では旧 `scene_amplification_ref` を要求しない。旧 `expressive_contract` を
満たすためにcutへ「圧力」「沈黙」「感情の変化」を追加しない。表現の具体化は既存の
viewer/event/motion/soundの該当領域で行い、必要な原作value参照は上流の実在する参照だけを使う。

source ledger/preflightのhashには新しいvisual計画とscene対応を含める。
story由来のevent所有・順序・reveal・handoff検証を残す。
sceneごとにvalue IDが既に対応していればそのまま継承し、なければstoryの原作価値契約を
本文として参照する。全scene/cutにvalue IDを配るための意味推定をコードで行わない。

## 7. 構造検証と版の扱い

新規v2の検証項目:

- 形式・必須外枠・型・既知の版。未知のキーを黙って削除しない。
- research/storyの実在・run内パス・bytes hash。
- storyと同じscene集合・順序・一意性。空のscene配列は不正、全sceneのnotes空は正常。
- notesが文字列配列であり、記載した項目は非空。最低件数・最低文字数・特定の感情語は要求しない。
- continuityのsource pointerが解決でき、対象sceneが実在する。新規asset/cut IDは要求しない。
- p300までの境界で本番生成ファイルを作っていない。
- p400/manifestの版、source hash、scene対応、受領notesが整合する。

書式や参照で検出できない解釈の忠実さ・演出の適否を検証済みと称しない。
禁止単語の正規表現、感情の個数、全欄の充足率による合否判定は作らない。

| 入力の版 | 挙動 |
| --- | --- |
| 既存v1 adaptation | 従来validatorとreaderで読取・再開。v1の要件を一括緩和しない |
| 既存markerなし | 既存のlegacy互換経路を維持。自動v2認定はしない |
| 新規v2 | 新validator、本文と疎なメモによる下流authoring |
| 未知版、v2と旧p300 amplificationの混在 | 明確な構造エラー。旧fallbackへ落とさない |
| v2 p300とv1 p400、またはsource hash不一致 | 下流をstaleとし、新規生成へ進めない |

story側の `adaptation_value_contract: required_v1` は原作保護の契約として保持できる。
p300以降はv2の明示分岐でそのsource/event/value整合性を検証する。
旧markerを消して検証全体を通り抜ける実装にしない。

既存runの自動移行はしない。新規runで切り替え、既存runは元の入力を保持して再開する。
`toc/p400_rebuild.py` は現在 `visual_value.md` を保存する契約なので、p300差替えを
そのまま流用して安全な移行と称してはならない。既存runのp300再設計は別の明示的操作として扱う。

## 8. 完了条件と残る境界

p310: authorが全入力と全sceneを扱い、新形式を書き、構造検証が通っている。
p330: 上流bindingsと下流が読める形式が確定し、成果物・state・index・orchestration結果が整合している。
任意選択をユーザーが求めていない場合、追加承認待ちを発生させない。

p400自身の `dramatic_question` / `value_shift` / `causal_turn` や定型blueprint等は別の制約である。
本実装はp300由来の旧amplification再導入を除くところまでを必須範囲とする。
全工程で静かなsceneや未解決の結末を自然に扱えるかは、p400独自規則も含む次の検証課題として残す。
