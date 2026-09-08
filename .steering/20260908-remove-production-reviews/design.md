# Removal design outline

このファイルは調査に基づく削除設計の入口。詳細は inventory.md と inventory/*.md。

## 進め方

1. runtime入口と進行判定の双方から依存を追う。
2. 独立したreview-onlyモジュールは呼出元と一緒に削除。作成・通常検証と混在する関数は分離する。
3. `passed` を偽造したり全stageを `preapproved` に切替えたりせず、レビュー証跡を読む/書く経路そのものを外す。
4. p-slot/state/UI/旧run互換を更新する。古い `review.*` / `eval.*` 値を生成条件として読まない。履歴は書き換えない。
5. workflow/docs/skills/agent instructions の必須review規定を同時に更新し、後の作成agentが再導入しないようにする。
6. レビューの必須性だけを固定するテストを廃止し、通常のデータ・画像・動画処理テストを保つ。

## 削除後の受入条件案

- standard/preapproved のどちらを旧clientから受け取っても、制作reviewer/critic/aggregatorを起動しない。
- review/aggregate/audit report が存在しなくても、正常な入力は各制作stage、画像生成、ナレーション/TTS、動画生成、renderへ進める。
- 任意の品質スコアや `review.status` の値で進行が止まらない。
- 壊れたJSON/YAML、参照先不存在、無効な生成request、ファイルdecode失敗、出力provenance不一致は通常の処理エラーとして検出する。
- 過去runのreview失敗/未作成がresume阻害条件として残らない。
- 固定slot、UIラベル、文書、スキルに「レビュー証跡が必須」の残存経路がない。
