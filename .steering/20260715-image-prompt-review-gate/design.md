# Design

## Canonical flow

1. p620 が `first_frame_visual_plan` から provider prompt draft を compile する。
2. p630 hard review と p640 semantic agent review が、正本 story/cut、asset dependencies、時代、候補 prompt を比較する。
3. reviewer は source artifact を編集せず、failed selector と修正理由を返す。
4. producer repair は failed selector の `first_frame_visual_plan`、人物・物・場所ID、references を修正する。
5. orchestrator が v2 payload を deterministic compiler で再生成し、request Markdown と immutable snapshot を再 materialize する。
6. reusable asset bible が変わった場合は、`asset_plan.md` へ projection し、共通 asset compiler で asset request/snapshot を再生成する。変更 asset を先に再生成してから scene snapshot の reference hash を再束縛する。
7. deterministic story-consistency report も同じ revision から再生成し、fresh semantic review が通った revision だけを p650 frozen として p660 へ渡す。

## Review projection rule

上流キーは画像 prompt の必須ブロックと一対一ではない。reviewer は cut ごとに次を判断する。

- include: この一枚で見える必要がある具体的な人物、物、場所、状態、時代要素
- omit: 後続motion、内部ID、観客理解、因果説明、他cut用情報、不要な参照
- add: 上流意味を描画可能にする姿勢、視線、手足、距離、素材、光、時代整合の具体化
- replace: 抽象語・制作メタ・矛盾した否定文を、同じ物語事実を保つ可視表現へ置換

## Temporal boundary

`must_not_advance_beyond` は progression review 用の境界であり、provider prompt の否定文ではない。明示された reveal / future outcome だけを `not_yet_happened_in_still` へ渡す。肯定側の must-show と否定側が衝突する場合は semantic review を fail する。

## Revision integrity

`image_generation.api_prompt_payload.prompt` は compiler output、`image_generation_requests.md` と snapshot はその派生物とする。producer が派生物だけを直すことを禁止し、repair 後の同期を orchestrator の責務にする。

asset prompt も `video_manifest.md.assets -> asset_plan.md -> shared asset compiler -> asset request/snapshot` の一方向 projection とする。既存 output があっても、時代、fixed prompt、visual subject、reference input が変わった場合は旧 prompt/source digest を再利用しない。
