# p420 未登録素材 — 実装結果

2026-09-26。既存のp400 scene author出力に `asset_requests` を追加した。
追加のLLM工程は設けず、既存の構造修正ループで不正な根拠や割当を修正する。

## 完了した受け渡し

`asset_requests` → source pointer/引用/scene・beat範囲/使用cutの検証 → 安定した素材IDへの解決 →
cut dependencyと参照パス → manifest asset bible → p500 inventory/plan → asset-stage request files。

`cinematic_direction.json` は元のregistryと拡張registry、解決記録を保存する。
読込時とrebuildでも再解決し、registry・参照パス・bibleが保存後に変われば検出する。
既存のasset_requestsなしdirectionは引き続き読める。

## 確認したケース

- 未登録の手紙と人物が、実際のp500素材作成リクエストファイルまで届く。
- sourceにある場所も登録できる。
- 同じsource identityを複数sceneで使っても、参照画像は一つの素材IDへまとまる。
- 同名でも別のsource identityは自動統合しない。既存の同名候補があれば再利用/別物の判断を明示する。
- 既存素材の外観は変えず、再利用の引用根拠はp500へ引き継ぐ。
- 存在しないpointer、引用違い、別sceneの根拠、未使用候補、重複ID、不正なcut参照を拒否する。
- 後続beatの素材を早いcutへ割り当てることを拒否する。無関係な早い引用を足しても回避できない。
- 自由なreference_descriptionは素材生成へ渡さず、原作で確認した対象名を被写体名にする。
- 解決後のsource roleによりbase registryが自己変更しない。
- asset bibleを落としたり、拡張registryの参照パスを改変した場合に検証が失敗する。
- fixtureではscene数とLLM呼出し数が一致し、素材検出用の別turnは増えていない。

## 検証結果

関連17テストファイル: **297 passed、24 subtests passed**。
その後、複数sceneでの再利用と場所素材の2ケースを追加し、p420専用ファイル全体を再検証: **21 passed**。
これらの件数は一部重複するため合算しない。

独立したcode reviewを実施し、同名の既存素材の重複、自由な外観説明の流入、再利用の根拠欠落を修正した。
再確認で具体的なp420→p500のルーティング失敗は見つからなかった。

`validate-slot-contract.py`、`validate-pointer-docs.py`、変更Pythonのcompileall、`git diff --check` も成功。
LLMの返答はテスト用stub。providerへ画像/動画/音声生成は依頼しておらず、リクエスト作成までを一時fixtureで確認した。

## 検証の限界

コードが確認するのはsource文字列・引用・使用関係とIDの整合性。
原作の意味から物理的対象を見分けること、同一対象かの判断、列挙漏れの有無は既存LLM authorの仕事であり、
この構造テストで漏れが絶対にないと保証したわけではない。実モデルによる原作別の列挙精度は未検証。
