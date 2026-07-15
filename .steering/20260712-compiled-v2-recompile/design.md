# Design

## Request routing

- v1 asset item: existing direct prompt regeneration/update。
- v2 scene item: compiler-aware recompile transaction。
- mixed selection: v2 transactionを完了後、v1更新を行う。v1失敗時も全対象成果物をrollbackする。

## Editable plan surface

App-server は自由形式promptではなく visual plan patchを返す。binding ID、references、source grounding、not-yet/reveal境界は変更させない。patch対象は現在の可視瞬間、人物状態、構図、光・素材だけとする。

## Transaction

1. `run_artifacts` と `scene_request_revision` lockを取得。
2. manifest/request markdown/snapshotをcapture。
3. selected cutのplanへpatchを適用。
4. existing IR dependenciesとreferencesでcanonical compilerを実行。
5. planとpayloadをmanifestへ保存。
6. filterなしの `_materialize_scene_requests` を実行。
7. selected itemのrevision変更と未選択item保持を検証。
8. 失敗時は3ファイルをrollback。

## Frontend

成功後はAPI response promptをローカル上書きせず、requests endpointから再取得したcompiled promptを表示する。v2対象がある場合は再compileであることを確認dialog/statusに表示する。
