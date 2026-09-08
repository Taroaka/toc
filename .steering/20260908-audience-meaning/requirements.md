# 観客の理解と意味の設計

## 要求

英雄の旅を導入済みの ToC に、観客の理解の推移、反復による意味の変化、世界観を行動から
伝える方法を組み込む。任意の物語で使える抽象的な authoring 指針とし、作品固有の人物・
場所・小道具・出来事を汎用ルールへ入れない。

## 完了条件

- story → visual_value → script/cut → asset の既存の記述先へ接続している。
- 成長、善悪の反転、帰還、教訓、象徴の反復、固定回数を必須にしない。
- 悲劇、群像、人物が変わらない作品、日常、謎を残す結末、解説でも適用・省略を選べる。
- 観客の理解、人物の認識、世界内の事実、感情を区別し、reveal と source 境界を守る。
- 新しい schema、mandatory marker、validator、production review stage を追加しない。
- 「キャンベル17段階」と12段階の表の不一致、および単純な圧縮という説明を修正する。

## 根拠と範囲

ユーザーが前ターンの三方向を承認し、「どんな物語でも作れる抽象的な内容」を希望。
既存の docs/story-creation.md、docs/affect-design.md、docs/adaptation-value-amplification.md、
docs/script-creation.md、docs/implementation/asset-bibles.md と現行テンプレートを根拠とする。
対象は制作ガイド、テンプレート、Story の実際の生成 prompt の執筆指示。
実際の run 作成、生成 API 呼び出し、UI、runtime schema の変更は含まない。

調査で frontend の Story Architect / Scene Author は文書本文を読まないと判明したため、
共通の任意指針を Architect / single Scene Author / batched Scene Author / repair に接続する。
既存の audience_knowledge / audience_knowledge_delta / reveal_contract と下流投影を利用する。

判断基準は「この作品の事実・意味・結末を保ち、観客に伝わる具体的な表現へ落とせるか」。
手法に合わせた筋の追加や、全作品への同一構造の強制はしない。
