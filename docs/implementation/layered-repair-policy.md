# LLM工程の補正を分離する方針・後続工程への引き継ぎ

## 目的

LLMの出力が検証に落ちたとき、正常な内容を再生成せず、失敗した箇所だけを補正する。
検証器やスキーマを緩めて通すことはしない。共通の構文修復とp200の項目補正は
`.steering/20260927-layered-repair/` の作業対象。別スレッドはp330以降を対象にする。

## 1. JSON構文修復

完全に解釈できるJSON objectの末尾に余分な `}` が一つある場合など、内容不変を保証できる
正規化はコードで行う。LLMを呼び直さず、LLM補正予算も消費しない。元の応答hashと修復receiptを保存する。

その他の対応可能な構文不正は、構文専用の文字位置差分で直す。元の「物語を作れ」という指示を再送しない。
キー・値・文章・ID・構造を変えないことをコードで検査する。現実装のLLM syntax patchは、
文字列外のカンマ・空白だけを変更できる。途中で切れた内容、重複キー、複数document、
曖昧な引用符や構造を推測して補完しない。

共通部品: `toc/json_syntax_repair.py`、`toc/story_author_runtime.py`。
構文専用patchの参考: `toc/story_syntax_patch.py`。

## 2. 項目単位の補正

対象: 不正な参照ID、間違った型、欠けた必須フィールドなど、実際の不正箇所を特定できるもの。
validator側がJSON Pointer、現在値、期待型、許可IDと名称・意味、関連sourceを特定する。
集約コードだけを見て、正常な別sceneにも同じエラーを直すよう要求しない。

LLMへ渡すもの:
- 対象unitの必要な文脈、元の依頼と固定制約
- 正確な失敗path、現在値、エラーコード/文言、期待する型と候補
- 参照IDに対応する実在レコード（ID一覧だけで意味を推測させない）
- 元のunitのdigestと変更許可path

LLMは完全なdocumentではなく、変更pathと修正値のoperationsだけを返す。
閉じたpatchスキーマをAPIの `output_schema` / `outputSchema` に直接指定する。
単にプロンプトへ形式を記載するだけにしない。全sceneをJSON文字列に包んで再出力させない。
柔軟なobject値だけJSON文字列にする場合は、その小さい値を厳密にdecodeしてから適用する。

コード側の必須制約:
- 対象IDとbase digestが一致すること。
- validatorが許可したpathだけ変更可能。root置換、指定外path、他のunit、入力資料は変更不可。
- 正常な隣接array要素と未変更フィールドを保持する。
- 同じpathの重複、重なったpath、不正型、許可外ID、何も変わらないpatchを拒否する。
- 削除を許すなら、診断された不正IDのarray要素だけ。必須arrayを空にしない。
  登録されていない役割を、無関係な既存人物IDへ置き換えて意味を変えない。
- patchはdeep copyへ適用し、元のvalidatorと影響範囲の検証を再実行してから採用する。
- patch自体が不正でも同じ差分形式で補正を続け、正常なscene全体の再執筆へ自動拡大しない。

p200の参考実装: `toc/story_field_repair.py`、`toc/story_author_pipeline.py`、
`scripts/author-story-with-codex.py`。story_field_repairのpath/ID taxonomyはp200専用なので、
p330/p420へそのまま流用せず、各stageの診断adapterを作る。

## 3. 物語内容の補正

対象: 因果・前後の状態・情報開示・演出の責務など、値の形式だけでは解消できない矛盾。
該当cut/sceneと必要な隣接contextだけを担当authorへ戻す。採用版、元の出来事、
無関係なscene、完了済み画像を保持し、意味を扱う修正であることを履歴に残す。
単純なID間違いや括弧の間違いを理由にこの経路へ入れない。

## 4. 対象外エラーと実行管理

通信、認証、quota、ディスク、権限、外部編集との競合、未知のコード例外は内容補正から分離する。
既存の `RepairSession` / run lease / checkpointを再利用し、再開で試行予算をリセットしない。
非収束・上限到達は原因と候補を保存して停止する。新規runを作って回避しない。
修正済み候補の採用後は、依存する派生requestだけ再構築する。実画像の欠損・破損は
対象画像だけ再生成し、現在のrequest/provenanceに対する完了検証を行う。

## 5. 別スレッドでの修正対象

- p330: `toc/visual_value_authoring.py`、`toc/visual_planning_contract.py`
- p420: `toc/p400_authoring.py`、`toc/p400_projection.py`
- 画像prompt: `toc/image_prompt_compiler.py` と所有authorへの戻し処理
- 必要に応じてp500/p650のrequest materialization
- p700以降は別途対象を明示して適用

共通JSON decoder・p200・story CLIはこのスレッドで変更中/変更済み。
作業開始時に最新ファイルと `.steering/20260927-layered-repair/tasks.md` を確認し、
他スレッドの変更を戻さない。共通部品を変更する必要がある場合は所有者を調整する。
稼働中runやサーバーを無断で止めず、失敗runのstate・予算・成果物を書き換えない。

## 6. 完了条件

fake LLMで実際に失敗する出力を作り、次を確認する。
- 余分な括弧の修復で追加のLLM呼び出しが0回。
- ID一つの修正で、指定path以外の内容が一致する。
- 指定外の文章・他scene・所有event変更を含むpatchが拒否される。
- 正しい出力スキーマがAPIへ直接渡される。
- 修正後に元のvalidatorが合格し、次の工程へ進む。
- 正常な上流と生成済みメディアの再実行が0回。
- 構文・項目・物語・通信をログで区別できる。
