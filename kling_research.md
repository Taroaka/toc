# Kling 3.0 / Omni Research

更新日: 2026-03-23  
対象:

- 指定記事: [〖実写AI動画はこれ一択〗初心者でも使いこなせる「Kling 3.0 / Omni 」全て解説します。](https://note.com/noz_tanaka/n/n553795d4619a)
- `note.com` 上の `2026-03-01` 以降の Kling 3.0 / Omni 関連記事
- Omni のキャラクター参照機能が API でも同様に使えるかの確認

このメモは **Kling ガイド本体を直接更新する前の調査レポート**。  
確認済みの事実、記事由来の経験則、API では未確認の推測を分けて扱う。

## 1. 指定記事から抽出した有用な prompt 術

## 1.1 採用するもの

- **スタートフレームと 1 カット目を同期させる**
  - 開始画像と cut 1 の内容がずれると Kling が不安定になりやすい、という運用知見。
  - これは UI の話に見えて、API でも `first_frame` と最初の意図を揃える設計にそのまま転用できる。
- **カスタムマルチショット前提で、cut ごとに prompt を分ける**
  - 1 本の長文で全展開を抱え込まず、shot 単位で指示を分割する。
  - ToC の `1 clip = 1 intention` とかなり相性が良い。
- **複数本生成して、良い cut を選ぶ**
  - prompt 改善だけでなく selection loop を前提にする。
  - Kling を「一発決め」ではなく「比較して拾う」運用に寄せるべきという話。
- **5 要素の shot prompt 型**
  - `タイトル / サブジェクト / カメラ / アクション / ボイス`
  - 記事としては有用で、ToC 内の shot card として採用する。

### 補足方針

- API 側でも、`first_frame` と cut 1 の同期を基本ルールにする
- API 側でも、1本の長文 prompt ではなく shot / cut 単位で prompt を分ける
- API 側でも、単発生成ではなく複数生成して良い cut を選ぶ selection loop を前提にする
- API 側でも、`タイトル / サブジェクト / カメラ / アクション / ボイス` を shot card の基本要素として使う

## 1.2 不採用とするもの

- **1 本 15 秒に収まる scene 粒度へ分解する**
  - 1 クリップで起こす出来事を増やしすぎない、という方向性自体は妥当。
  - ただし採用ルールとしては粗く、今回の運用判断では不採用。
  - 指定記事内の「1シーン3秒程度」の実務感を優先し、**API 運用では 1シーン3秒程度を基本ルールとして採用**する。

## 1.3 採用候補だが一次確認は弱いもの

- **1 cut 3 秒を初期値にする**
  - 記事上は UI 経験則として説明されている。
  - ただし今回の運用判断では、上記の通り **API 側の基本ルールとして採用**する。

## 1.4 記事の強い主張で、そのまま正本に入れない方がよいもの

- 「実写はもう Kling 一択」
- 「人間俳優以上の演技」
- 「絶対にできなかったことが Kling ならできる」

上記は販促色が強く、比較検証の一次情報としては弱い。

## 2. Kling ガイド改善に使えそうな論点

今回の調査から、今後 `workflow/playbooks/video-generation/kling.md` に反映候補として強いのは次。

- **Custom Multi-Shot 節**
  - start frame と cut 1 の同期
  - API では 1シーン3秒程度を基本にする
  - shot ごとに prompt を分ける
- **shot card の型**
  - `タイトル`
  - `サブジェクト`
  - `カメラ`
  - `アクション`
  - `ボイス`
- **voice / audio direction の独立節**
  - セリフ
  - 環境音
  - BGM
  - 発話の読みやすさ
- **selection loop の運用節**
  - 1 scene を複数生成
  - 良い cut を比較選定
  - prompt 改善と選定を分ける

## 2.1 記事群から正式採用する recurring prompt 術

- **reference 起点で始める**
  - pure text から作るより、reference image / element / subject 起点で組む
- **不変条件を毎回 lock する**
  - 顔、髪、服、持ち物、役割、環境 anchor を繰り返し固定
- **カメラは安定寄り**
  - motion 自体が主題でない限り、カメラは暴れさせない
- **見た目と motion を分離**
  - appearance は reference
  - motion は motion control / video reference / action prompt
- **lip sync は読みを崩してでも制御する**
  - 難読漢字をかなに直すなど、音声品質を優先する
- **speech-heavy では読みをかなに寄せる**
  - lip sync や音声生成で、難読漢字をひらがな化する運用が複数記事で示唆される

## 3. Omni のキャラクター参照機能は API でも同じか

## 3.1 記事が説明していること

指定記事では、Omni で次のような **UI 上の主体登録** ができるように読める。

- 顔、全身前、全身後ろなど複数画像でキャラクターを登録
- 名前を付ける
- Kling 側が説明文を生成
- 後続の動画生成でその主体を選んで再利用する
- 背景や建物も再利用対象として扱えるように読める

この説明は **プロダクト UI の persistent asset 管理** に近い。

## 3.2 API で確認できたこと

今回直接確認できた範囲では、**Omni API に同等の「登録して ID 参照する」仕様は確認できなかった**。

確認できたもの:

- PiAPI の Kling 3.0 Omni ドキュメントでは、
  - `@image_1` のような **その request 内での参照画像指定**
  - multi-shot
  - video reference
  が確認できた
- 同じ第三者系 docs では、
  - `Kling O1` に対しては Element Reference / Element Library 的な説明がある
  - `Kling 3.0 Omni` に対しては consistency 強化や video character subject の説明がある

今回確認できなかったもの:

- Omni での reusable subject library を作る API endpoint
- キャラクターや建物を登録して、後続 request で ID / alias 参照する API schema
- official first-party docs における Omni subject registry の明示

## 3.3 現時点の判断

**UI にある可能性は高いが、API 契約としては未確認** という扱いが妥当。

したがって ToC の設計は、少なくとも今の段階では次を前提にした方が安全。

- remote 側の Omni subject registry を前提にしない
- `character_bible` / `object_bible` を repo 側で正本管理する
- multi-angle の reference 画像や reference clip をローカル asset として持つ
- API request ごとに必要な reference を明示的に展開する
- alias を使いたいなら、**ToC ローカルの alias -> refs/prompts 展開**として実装する

## 3.4 設計 implication

今後もし official Omni API が公開されたら、次の二層構造にするとよい。

- 現行:
  - local alias
  - local refs
  - request 展開
- 将来:
  - provider-backed subject cache を optional 追加
  - ただし local 正本は維持

## 4. `note.com` 記事調査（2026-03-01 以降）

今回確認できた記事群:

- 2026-03-05: [Kling Motion Control 3.0 が公開/ Catch up on AI 2026.03.05](https://note.com/taziku/n/n315ec02bbef9)
- 2026-03-05: [AI動画トレンド 3Dキャラで100万再生をとってる動画の作り方 Nanobanana×Kling AI×eleven labo](https://note.com/masayume7310/n/nd51b08db5c9d)
- 2026-03-05: [動画生成AIはそれぞれ「守るもの」が違う― Sora / Veo / Kling / Vidu / Runway を制作視点で観察する](https://note.com/renz1116/n/ne92c3ae519c8)
- 2026-03-06: [Pollo AIのKling 3.0を触ってみた！画像生成から動画化まで、ワークフローで試してみた](https://note.com/syuu1500/n/nab29944481c0)
- 2026-03-06: [第5世代の動画生成モデル（Kling 3.0、Seedance 2.0）は危険すぎる - 検証報告会](https://note.com/creative_edge/n/nb71d78a940b9)
- 2026-03-07: [Kling 3.0 × Seedance 2.0 × Sora 2 実際に触り比べた体験レポ](https://note.com/pu_ta4416/n/n16f942f2ec3d)
- 2026-03-08: [動画生成AI〖KLING 3.0〗で「サラリーマンの日常」を描こうとして見えたAIの限界](https://note.com/vitnesstokyo/n/n0b784daee41d)
- 2026-03-08: [Klingの神機能で映画みたいなAI動画が生成できた！](https://note.com/re_76enree4/n/n2bc153b2b40e)
- 2026-03-09: [キャラの外見・声の一貫性を維持できる「Kling 3.0 Omni」の使い方・活用方法を解説](https://note.com/tanabe_fragments/n/nb6a7639728d3)
- 2026-03-09: [〖AI副業〗#038 Kling 3.0：15秒超えのAIアニメ制作が個人でもできる](https://note.com/pirock8745/n/n0ccec0f20260)
- 2026-03-10: [Kling AIで内臓が喋るシュールな動画を作る方法](https://note.com/romo_i/n/ndc0886767aee)
- 2026-03-11: [Kling Video V3 Motion Controlについて解説](https://note.com/hiroto141225/n/nbf07d639227c)

補足:

- `romo_i` の記事は Kling 3.x 全般評価ではなく lip sync のニッチ運用
- `renz1116` の記事は Kling 専用解説ではなく比較観察ログ
- それでも 2026年3月の Kling 実務感を補う材料として参照価値はある

## 5. 記事群から見えた recurring prompt 術

- **reference 起点で始める**
  - pure text から作るより、reference image / element / subject 起点で組む
- **不変条件を毎回 lock する**
  - 顔、髪、服、持ち物、役割、環境 anchor を繰り返し固定
- **multi-shot で 1 shot 1 action**
  - `ショット1 / ショット2 / ショット3` の形で、各 shot の主動作を 1 つに絞る
- **カメラは安定寄り**
  - motion 自体が主題でない限り、カメラは暴れさせない
- **見た目と motion を分離**
  - appearance は reference
  - motion は motion control / video reference / action prompt
- **まずは短い日本語 prompt で試す**
  - 日本語でも雰囲気理解が強いという感想が多い
  - ただし multi-shot では結局 precision が必要
- **lip sync は読みを崩してでも制御する**
  - 難読漢字をかなに直すなど、音声品質を優先する
- **start frame / storyboard を先に決める**
  - 初期フレームと shot 順序を決めてから motion を入れる方が安定する
- **5要素または近い shot card で整理する**
  - `タイトル / サブジェクト / カメラ / アクション / ボイス`
  - または `scene x character x action x style x camera`
- **speech-heavy では読みをかなに寄せる**
  - lip sync や音声生成で、難読漢字をひらがな化する運用が複数記事で示唆される
- **1分動画でも 15秒 x 4 本などに分けて考える**
  - 長い一本より、意味のある clip 群として組み立てる方が扱いやすい

## 6. 記事群から見えた Kling の強み

- **キャラクター一貫性**
  - Omni の主体 / Elements / reference 系が最頻出の強み
- **prompt 追従性**
  - とくに雰囲気、演出意図、映画的トーン
- **人物動作の自然さ**
  - 演技、表情、身体の滑らかさ
- **物理表現**
  - 水、布、反射、ライティング
- **storyboard 的に扱えること**
  - 単発 clip 生成より、scene 設計ツールとして語られている
- **音声 / 環境音**
  - 一部記事では heavy prompt なしでも音が乗る点が評価されている
- **動作フローの連続性**
  - 比較観察では Kling は「空間」や「世界」より、走る・振り向く・投げる等の action continuity が強いとされる
- **長めの native generation / storyboard control**
  - `15秒`, `multi-shot`, `custom storyboard` を workflow 上の利点とみる記事が多い

## 7. recurring caveats

- setup が面倒
- クレジットコストが高い
- 長尺では drift が出やすい
- prompt を何度もいじると world coherence が崩れることがある
- lip sync / pronunciation はまだ手当てが必要
- article によっては Pollo AI 経由など platform-wrapped で、direct Kling API と 1:1 対応しない
- prompt を細かく修正し続けると、world coherence がむしろ壊れることがある
- 速さや量産性より、1 clip あたり品質を取りにいくモデルとして語られることが多い

## 8.1 記事別メモ

### 2026-03-23 `noz_tanaka`

- 価値が高い点:
  - start frame と cut 1 の同期
  - custom multi-shot
  - 15秒に収まる scene 粒度
  - selection-first 運用
- 保留:
  - `タイトル / サブジェクト / カメラ / アクション / ボイス` は有用だが一次確認未了
- 注意:
  - 強い販促バイアスあり

### 2026-03-06 `syuu1500`

- 価値が高い点:
  - 先に参照画像で雰囲気を固める
  - 主役が埋もれない構図
  - 動画化しやすいシンプル構成
- 注意:
  - Pollo AI 経由の体験であり direct Kling UI/ API と同一視しない

### 2026-03-03 `vitnesstokyo`

- 価値が高い点:
  - 失敗知見が有用
  - 演技は強いが、空間や配役の world coherence は壊れやすい
  - 修正 prompt を足し続けるより、scene 分割や start frame 切替が安全

### 2026-03-08 `re_76enree4`

- 価値が高い点:
  - element reference + multi-cut
  - `寄りで感情 -> 光で転換 -> 引きで世界観` の3段ショット設計
- 注意:
  - 有料部分が多く、無料範囲だけではテンプレ完全取得は不可

### 2026-03-09 `tanabe_fragments`

- 価値が高い点:
  - Omni UI の主体登録運用
  - 2〜4枚の異角度画像
  - 声を安定させたいなら speaking video を先に作る
- 設計示唆:
  - API 契約は未確認でも、local asset 管理では参考になる

### 2026-03-11 `hiroto141225`

- 価値が高い点:
  - Motion Control は appearance と motion を分離する考え方
  - `character_orientation`
  - `keep_original_sound`
  - `elements`
- 設計示唆:
  - prompt 工夫より、reference asset と control parameter の管理が重要

### 2026-03-05 `taziku`

- 価値が高い点:
  - 具体 tips は少ないが、制作工程が `subject / background / camera / motion` 分離へ進むという方向感
- 注意:
  - 概念・将来予測寄り

### 2026-03-06 `creative_edge`

- 価値が高い点:
  - Element 登録は面倒だが有用
  - 10秒超で hallucination が増えやすい
  - 長文 prompt で全部制御する方式の限界
- 設計示唆:
  - node/workflow 的な分離管理に寄せるべき

### 2026-03-07 `pu_ta4416`

- 価値が高い点:
  - text だけでも高品質という体感
  - 水、布、反射など material realism が強み
- 注意:
  - 比較 impression 記事であり、prompt 術は薄い

### 2026-03-09 `pirock8745`

- 価値が高い点:
  - native 15秒の価値
  - multi-shot を storyboard tool として扱う
  - `scene x character x action x style x camera` の整理
- 注意:
  - 収益化文脈が強い

### 2026-03-10 `romo_i`

- 価値が高い点:
  - lip sync は prompt 以上に source image geometry に依存
  - 非人間 lip sync の niche hack
- 注意:
  - Kling 3.x 全般の guide へは限定的にしか反映しない

### 2026-03-05 `masayume7310`

- 価値が高い点:
  - subject binding + angle expansion
  - 4 x 15秒で組む short 設計
  - spoken line を quotes で入れる
  - ひらがな化で誤読を減らす
- 注意:
  - バズ系 3D キャラ short に強く寄った運用

### 2026-03-05 `renz1116`

- 価値が高い点:
  - Kling は motion continuity に強い、という比較観察
- 注意:
  - model-selection heuristic としては有用だが、prompt syntax の根拠にはしない
## 9. この調査からの当面の結論

- Kling 向け prompt guide は、
  - `start frame sync`
  - `multi-shot`
  - `1 shot 1 action`
  - `reference-first`
  - `selection loop`
  を前面化した方がよい
- 加えて、
  - `shot card`
  - `voice / lip sync 運用`
  - `appearance と motion の分離`
  - `material realism を狙う prompt の得意領域`
  も章として切り出す価値がある
- Omni の「主体登録」は、**UI 機能としては有望でも API 契約としては未確認**
- そのため ToC は、**ローカル asset 正本 + request 展開**の設計を維持するのが安全

## Sources

- 指定記事: [https://note.com/noz_tanaka/n/n553795d4619a](https://note.com/noz_tanaka/n/n553795d4619a)
- Kling AI Global: [https://app.klingai.com/global/](https://app.klingai.com/global/)
- PiAPI Kling 3.0 Omni docs: [https://piapi.ai/docs/kling-api/kling-3-omni-api](https://piapi.ai/docs/kling-api/kling-3-omni-api)
- klingapi.com features: [https://klingapi.com/features](https://klingapi.com/features)
- klingapi.com FAQ: [https://klingapi.com/ja/faq](https://klingapi.com/ja/faq)
- klingapi.com Kling 3.0 Omni: [https://klingapi.com/models/kling-3-0-omni](https://klingapi.com/models/kling-3-0-omni)
- klingapi.com Kling O1: [https://klingapi.com/models/kling-o1](https://klingapi.com/models/kling-o1)
- klingapi.com API docs: [https://klingapi.com/ja/docs](https://klingapi.com/ja/docs)
