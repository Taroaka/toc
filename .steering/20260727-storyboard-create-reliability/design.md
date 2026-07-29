# Design

## Architecture

```text
Create dialog
  -> POST /api/image-gen/runs/create/storyboard
  -> p680 canonical create pipeline
  -> cut image validation
  -> storyboard transaction
       1. validate all selectors/cuts/provider partitions
       2. compose storyboard PNGs into a staging directory
       3. build manifest + request contents in memory
       4. validate exact request bindings
       5. atomically commit PNGs, manifest, request
  -> strict storyboard validator
  -> completed
```

## API Contract

- `CreateStoryboardRunRequest.stop_target` は `p680` のみ許可する。
- storyboard route は `generate_images=True` と `create_mode=scene_storyboard` を固定する。
- frontend と headless helper は同じ専用 endpoint を使う。

## Selector and Partition Contract

- sanitize 後の scene selector を global set で検査する。
- render unit id は `<scene_selector>_unit<normalized_unit_id>` とし、global uniquenessを検査する。
- cut順序は変えず、provider duration min/max内の最少unit数へ分割する。
- UIはunit分割があり得ることを明示する。

## Transaction Boundary

- storyboard画像は run 配下の一時 staging directory に作る。
- manifest と video request は一時ファイルへ書き、内容検証後に commit する。
- commit前の失敗では staging directoryだけを除去する。
- commit中の失敗では、既存manifest/requestのbytesと、置換済みstoryboardの事前状態を復元する。
- state append はファイルcommit成功後だけ実行する。

## Exact Request Binding

既存 `_split_video_request_sections` と `_reviewed_video_request_binding` を再利用し、各 expected unit について次を検証する。

- exact title matchが1件だけ
- unexpected/duplicate sectionがない
- tool/output/duration/quality/aspect ratio/first frame
- prompt policy/compiler/source digest
- prompt本文と `prompt_sha256`
- negative prompt本文と hash
- references listと `references_digest`
- manifest render unitのreferences/output/payloadと一致

list field (`source_cuts`, `references`) は section parser で正規化して比較する。

## Frontend Polling

- 初回POST成功後はjob statusが `running` の間pollする。
- 固定30回の上限を置かない。
- `completed`, `paused`, `failed` をterminalとして扱う。
- status messageを各pollで反映する。
- polling helperを独立した pure async module にして fake fetch/sleep でunit testする。

## Headless Regression

- `--create-mode normal|scene_storyboard` を追加する。
- storyboard は `/api/image-gen/runs/create/storyboard` を選ぶ。
- storyboard route は画像生成必須なので `--create-mode scene_storyboard --no-images` を引数エラーにする。
- `storyboard_v1` assertion profileで state、manifest render units、storyboard画像、exact request bindingを確認する。

## Test Strategy

1. API validation: storyboard p650 rejection、p680 scheduling、duration boundaries。
2. Unit: selector collision、cut id collision、duration partition boundary。
3. Materialization: single/multiple unit、ordered refs、PNG size、state。
4. Transaction: compose/write failure注入後のrollback。
5. Validator: exact section、duplicate、prefix collision、prompt/reference/hash tamper。
6. Frontend unit: 30回超のrunning後も継続、各terminal state、message callback。
7. Headless integration: mode別endpoint/payload、invalid no-images combination、profile checks。
8. Regression: existing normal create、video approval、frontend build。
