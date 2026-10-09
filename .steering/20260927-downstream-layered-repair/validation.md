# Validation

変更した本番ファイル:
- `toc/downstream_repair.py` (new): stage diagnostics, direct closed patch schema, strict patch application, durable loop
- `toc/visual_value_authoring.py`: p330 syntax/field/semantic split, stored candidates, source/media preservation
- `toc/p400_authoring.py`: p420 bounded repair, no all-scene promotion, resume/reuse, real image projection validation
- `toc/p400_projection.py`: exact scene/cut identity on compiler diagnostics
- `toc/p420_assets.py`: typed asset request validation errors with request-local paths; resolution behavior unchanged

共通JSON修復、p200、共通RepairSession、稼働run/サーバーは変更していない。

ローカルレビュー:
- initial creative prompts are called only without a reusable candidate; invalid syntax never replays them
- patch API receives closed `output_schema` directly
- root/unscoped/overlapping/duplicate/digest/no-op/type/reference violations fail closed
- original structural validators and image compiler run again before adoption
- accepted neighboring scenes and saved resolved assets are reused; no media writes in these authors
- network/auth/I/O/source conflicts and unknown code exceptions are not passed to the content author
- no story-specific production branches or hardcoded story facts added
- no new external dependencies

検証:
- `tests/test_downstream_layered_repair.py`: 22 passed
- broader affected suites: 127 passed, 2 subtests passed (p330/p420/assets/frontend repair/resume/B-roll/image request preservation)
- final asset evidence context follow-up: downstream repair + asset suites passed
- `python scripts/validate-pointer-docs.py`: passed
- `git diff --check`: passed
- `python -m py_compile` for changed production modules: passed

実API・実画像生成は実行せず、fake providerとtemporary runで検証した。

## p200未コミット実装との整合後

- `story_field_repair.py`、`story_author_pipeline.py`、`author-story-with-codex.py`、`story_syntax_patch.py` の実処理を照合。
- p330/p420へ既存syntax-only patchを接続。キー/値/物語を書き換える構文patchを拒否し、同じ構文専用形式で再試行する。
- `unit_id` / digest / path / native値型をAPI schemaで制限。object/複合配列だけ局所JSON文字列に限定。
- 診断された未登録asset IDだけ削除可。元index基準の検証と末尾削除で正常要素を保持。登録済みID、必須source beat、空配列化は拒否。
- p200に残る全sceneへの補正拡大は引き継がず、正常なsceneを保持。
- p200/common source files unchanged by this task.
- affected authoring + common syntax/CLI regression suites: 111 passed
- final downstream regression: 28 passed
