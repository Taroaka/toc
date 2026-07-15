# Create Failure Observability Requirements

## Goal

Frontend create が画像生成前に失敗したとき、traceback を解析せずに停止 stage、処理 phase、画像生成未開始、失効した supervisor 結果を判断できるようにする。

## Success criteria

- semantic transport failure を構造化した state と create-job debug log に残す。
- `image_generation.status=not_started` と blocking stage/reason を明示する。
- 既存の `p600.supervisor_result.json` が後続 failure により失効したことを state に残す。
- semantic review 本体の失敗と producer repair 中の失敗を区別する。
- mock test のみで検証し、画像生成や新規 run 作成を行わない。

## Scope

- `server/image_gen_app.py`
- `tests/test_image_gen_server.py`
- 必要な state contract documentation

## Out of scope

- semantic QA の合否条件変更
- timeout、retry、部分継続方針の変更
- 既存 run の書き換え
- 実画像生成
