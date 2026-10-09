# p330以降の限定補正

共通方針は [layered-repair-policy.md](layered-repair-policy.md)。p200および共通decoderは変更せず、
`toc/downstream_repair.py` のstage診断adapterをp330/p420に接続する。

## 実行境界

- p330: `toc/visual_value_authoring.py`。scene selector、notes、Bロール、continuity referenceを診断する。
- p420: `toc/p400_authoring.py`。cutの型・必須値・参照IDと、asset requestのsource pointerを診断する。
- p400画像projection: `toc/p400_projection.py`。画像compilerの失敗にsource sceneとcut位置を付ける。
  p420 author内でも同じprojection/compilerを実行するため、曖昧な選択肢や時間帯矛盾は該当cutへ戻る。
- p500/p650のrequest materializationはコードによる派生処理であり、別のLLM再生成ループは追加しない。
  後続からのhandoffでは保存成果物を再検証して対象だけ補正する。
- narration用scratch/prompt生成スクリプトはLLM APIを呼ぶauthorではない。この変更で新しいAPI工程は追加しない。

## Protocol

初回authorのresponseはbinding付きcandidateとして保存する。共通のreceipt付きdecoderを使用し、
内容不変のコード修復ではLLM呼出しと補正予算を増やさない。それでdecodeできない場合でも、
p200の `toc/story_syntax_patch.py` が扱える完全・平衡・曖昧でないJSON候補なら、構文専用の文字位置差分を要求する。
APIへ `SYNTAX_EDIT_SCHEMA` を直接渡し、文字列外のカンマ・空白だけをコードで適用する。
キー・値・文章・ID・構造を変える差分は拒否する。切断、重複キー、曖昧なtoken等の対象外構文はraw候補と診断を残して停止する。
同じbindingで再開しても、構文失敗を理由に初回の物語生成promptを再送しない。

項目補正の入力はJSON Pointer、現在値（missingを区別）、期待型/enum、IDに対応する実在レコード、
base digest、必要なsource context。返す形式は以下のみ。

```json
{"unit_id":"source-scene-id","base_digest":"...","operations":[{"path":"/cuts/0/character_ids/0","value":"registered-id"}]}
```

この閉じたschemaを `output_schema` に直接渡す。対象ID、base digest、pathをenumで固定する。
文字列・整数・文字列配列はnative JSON値とし、pathごとの期待型をAPIの差分schemaにも指定する。
柔軟なobject/複合配列だけ局所JSON文字列としてstrict decodeし、重複key/NaNを拒否する。
`allow_remove` が明示された未登録asset IDの配列要素だけ `value: null` で削除できる。
登録済みIDや必須source beat、正常な隣接要素は削除できず、ID配列を空にしない。
全差分を元のindex基準で確認し、置換後に末尾indexから削除するため、複数削除でも正常な要素はずれない。
codeはroot変更、指定外path、重複/重なり、digest不一致、不正型/ID、無変更patchを拒否する。
意味補正でcutやasset requestを再執筆しても、そのunit IDは変更できない。
採用前に元のvalidatorと画像compilerを再実行する。

構文専用差分と型・参照補正の既定モデルは共通の `DEFAULT_REPAIR_AUTHOR_MODEL`、意味補正は担当authorのmodel。
各呼出しは共通runtimeの独立したread-only threadを使い、過去の会話transcriptを複製しない。

## 保持と停止

- `RepairSession` の永続ledgerと予算を再利用する。patch不正でも全文生成へ戻さない。
- p420は採用済みsceneをキャッシュし、後続の失敗や再開で再生成しない。
  research/storyとresource bindingが同じ既存成果物も再検証して利用する。
- 各authorは自分の成果物とログだけを公開し、正常な上流・画像を変更しない。
- source変更、通信/認証、I/O、未知の例外は内容補正に変換しない。失敗ログにsyntax/content/runtimeの区別を残す。
- 参照の意味が一致する候補がなければ無関係な既存IDに置換しない。
- 診断adapterのない集約エラー、余分なscene、既存scene IDの入替えなど、変更範囲を確定できないものは停止する。
  非収束を理由に全sceneへ再生成を拡大しない。対応を増やす際は具体的なpath診断と保護テストを追加する。

検証: `tests/test_downstream_layered_repair.py` およびp330/p420、asset requests、resume、Bロール、画像request保持の既存テスト。

## p200との整合

p200の未コミット実装を参照し、構文専用差分・型付きpatch・限定削除・対象ID/digest固定を揃えた。
pathと参照のtaxonomyは後続工程専用で、p200のfield診断をそのまま流用しない。
p200に残るscene-setへの補正拡大は採用せず、今回の依頼どおり正常なsceneを保持する。
