# Drawable image prompt runtime requirements

## Goal

p600 の各 cut について、設計用の全構造をそのまま provider prompt に展開せず、静止画として描画に必要な情報だけを選択して `image_generation.api_prompt_payload.prompt` に凍結する。レビュー表示、実送信、再開、並列実行のすべてが同じ凍結 payload と provenance を参照する。

## Canonical flow

`scene_event -> cut_contract -> first_frame_visual_plan -> drawable_prompt_ir -> api_prompt_payload -> request_snapshot -> Codex app-server imageGeneration -> output provenance`

## Functional requirements

1. scene/cut の prompt compiler は一つの共有実装を使う。frontend scaffold と manifest materializer が独自に prompt を組み立てない。
2. compiler は `first_frame_visual_plan` と asset bible/reference を入力に、静止画で見える情報だけを `drawable_prompt_ir` へ選択する。
3. 人物、小道具、場所、光、構図、blocking、reference continuity の各断片は、その cut に具体的な値がある場合だけ prompt に含める。空 block、generic filler、内部キー名は含めない。
4. `motion_brief`、前後 cut の進行説明、scene/cut ID、source selector、review/debug/validation metadata は API prompt に含めない。
5. `image_generation.prompt` は読み取り互換だけに残し、payload がある production request の選択・実行条件にはしない。
6. `image_generation_requests.md` は人間レビュー用 projection とし、実行側は同時生成された versioned JSON snapshot を正本として読む。
7. snapshot item は exact prompt、prompt SHA-256、reference path と content SHA-256、destination、compiler/policy version、source digest を持つ。送信直前と既存 output 再利用時に一致を検証する。
8. Markdown prompt 更新は `api_prompt` fence を壊さず、snapshot を再 materialize するか stale として fail closed にする。
9. Codex app-server の request-bound production lane は、一つの request item につき一つの image generation item を受理し、実際に送った prompt と reference hash、turn/item/saved path を provenance に残す。
10. 同一 run の create/resume は lease により多重実行しない。複数 run の画像生成は cross-process global semaphore に従う。serial fallback は全 process で一件だけにする。
11. resume は成功済み item を削除せず、現在の prompt/reference provenance と一致する output だけを再利用し、不一致 item だけを再生成する。
12. gate は条件付き completeness、内部情報 leak、hash/provenance、空レビューを検証する。対象 0 件の semantic review は pass にしない。

## Compatibility and rollout

- `image_api_prompt_v1` の既存 reader を受け入れるが、新規 materialization は `image_api_prompt_v2` と versioned snapshot を生成する。
- legacy Markdown-only request は明示的 compatibility lane でのみ読み、production の既定は snapshot-required とする。
- asset stage の prompt compiler contract は維持し、scene/cut 専用 IR と混同しない。
- 既存 run artifact は一括書換えしない。再 materialize した run から v2 に昇格する。

## Success criteria

- 人物なし cut に人物 block が出ず、小道具なし cut に小道具 blockが出ず、空オブジェクトの文字列化や固定テンプレート文が出ない。
- 内容の違う隣接 cut の prompt が、それぞれの可視差分を持つ。
- request preview の `api_prompt` と snapshot の exact prompt と app-server send-time prompt hash が一致する。
- prompt/reference を変えると既存 output は再利用されず、変えていない成功 item は resume で保持される。
- 2 process から実行しても global image concurrency 上限と per-run lease が守られる。
- focused tests、回帰 tests、fast verification、frontless backend create (`--no-images`) が通る。

## Out of scope

- provider や動画生成 provider の変更
- 既存の物語・scene/cut authoring logic 全体の再設計
- 過去 run の全画像再生成
- UI の大規模な見た目変更
