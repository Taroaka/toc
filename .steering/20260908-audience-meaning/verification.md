# 検証記録

## 自動チェック

- `python scripts/validate-pointer-docs.py`: passed。
- `python -m pytest tests/test_pointer_docs.py -q`: 1 passed。
- Story / cut 投影 / pointer 関連8ファイルのテスト: **33 passed**。
  - tests/test_story_audience_meaning.py
  - tests/test_story_authoring.py
  - tests/test_story_author_pipeline.py
  - tests/test_story_author_runtime.py
  - tests/test_story_author_integration_contract.py
  - tests/test_story_causal_connection_prompts.py
  - tests/test_story_lifecycle_downstream_projection.py
  - tests/test_pointer_docs.py
- 新規テストは実装前に instruction の未定義で失敗し、接続後に成功。
- 未解決の結末と変わらない関係という異なる入力を、同じ Architect / single / batch / repair
  prompt 経路で確認。symbol registry が空でもそのまま保持し、source / plan / 入力を変更しない。
- FakeTurnRunner の実際の pipeline 呼び出しでも、Architect / batch / repair の各 request が
  指示を受け取ることを確認。single builder は独立した直接呼び出しで確認。
- cut 投影のテストは authored delta の上書きを実装前に再現し、修正後に成功。
  nonblank / null / empty / whitespace、primary beat との対応、入力不変を確認。
- pytest-cov / coverage は環境にないため、標準ライブラリの trace で変更行を確認。
  本タスクが追加した実行可能行11行中11行を実行（変更範囲100%。モジュール全体の coverage ではない）。
  frontend の並行作業による別関数の変更行は測定対象から除外した。
- 初回のコメント追加時は YAML の読み取り結果が同一。レビュー後、本変更で変更した値は
  success criterion の適用条件と audience_state_before/after の説明文の3箇所のみ。
  本変更による schema/key の追加・削除はない。並行作業による template の別変更は保持。
- 追加したローカル文書リンク5件と見出しが解決でき、code fence の対応が保持されている。
- 既存 stage readset は変更文書を含む。ただし frontend の直接 Story author は本文を読まないため、
  共通 instruction をコードに接続している。

## 設計上の適用確認（生成品質の実測ではない）

| 物語の性質 | 指針が許容する扱い |
| --- | --- |
| 悲劇 | 喪失や不確かさを残し、救済を追加しない |
| 群像 | 複数主体の信念・解釈を併存させる |
| 変わらない人物・日常 | 理解の維持・補強・深化を扱う |
| 未解決・非線形 | 開示済みの情報と未解決の問いを提示順に区別する |
| 解説 | 人物の成長や宗教的要素を加えず、世界の規則を観察可能にする |
| 反復のない作品 | 象徴・追加場面・画像 asset を要求せず手法を省略する |

外部生成 API を使った作品生成は実施していない。今回の自動チェックは指示の接続、入力保持、
既存契約の回帰を検証するもので、観客の反応や LLM の作品品質を保証するものではない。

## 独立レビュー

初回の指摘に基づき、必須に読める主人公・変容・帰還の表現、lifecycle の exact path、
観客の知識と affect の記述先、実在文化と創作世界の区別を修正した。
実 pipeline の request 検証と cut 投影テストを追加。最終レビューでは本変更に起因する
残存 regression は確認されなかった。実 production run と並行作業の非対象差分は未検証。
