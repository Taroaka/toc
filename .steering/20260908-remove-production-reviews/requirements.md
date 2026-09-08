# Production review removal — requirements

## 今回の依頼

ユーザーは、レビューなしモードとの切替に依存せず、制作中にレビューを挟むエージェントと、各成果物にレビューの存在・合格・点数を要求する監査の削除を希望し、まず全対象の洗い出しを求めた。

## この調査の完了条件

- 起動側、レビュー/採点本体、証跡監査、進行 gate、設定/state/UI、正本とミラー、テストの依存関係が分かる一覧を作る。
- p230 のみでなく research → story → scene/cut → asset/image → narration → video/render/QA、CLI、frontend create、resume を対象にする。
- standard/preapproved 両方を調べ、決定論的な合格レポート生成も含める。
- キーワード一致だけで削除を決めず、削除・分離・保持・隣接範囲を分類する。
- 調査中は production code、run 成果物、state、server 起動状態を変更しない。

## 削除設計の基本範囲

削除候補: reviewer/critic/aggregator、再評価ループ、レビュー結果に基づく repair、自動採点と合格点 gate、レビュー文書/項目/人数/順序/digest/署名の監査、監査の合格要求、レビュー必須slot、レビュー有無modeと疑似合格証跡。

分離対象: schema/参照/生成ファイル検証とレビュー証跡監査が同居した verifier、grounding の資料解決と「読んだ/監査passed」証跡 gate、request freeze と「reviewed」状態、画像候補選択と「approved」状態。

保持候補: 実際の作成エージェント、データ読み込み/型/ID参照の整合、実ファイルの存在/デコード、requestとprovider出力の結合、アクセス制御/lock/パス制約。制作物の品質を決めるスコアや証明書とは別物。

人間が画像や音声を選ぶUI、任意の編集、候補管理は関連箇所として列挙する。必須レビューgateを取り外すことと、候補選択UI自体を削除することを混同しない。

## 対象外

過去の output/、別 checkout の .claude/worktrees/、marketing/、kindle/、improve_claude_code/、汎用のソフトウェア開発code-review/security-reviewスキル。これらをproductionレビュー廃止の一括削除へ巻き込まない。
