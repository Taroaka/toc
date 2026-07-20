# Design

## Boundary

動画の設計書と provider prompt を分離する。

1. 上流設計は物語上の責務、event、reveal、開始・終了状態を保持する。
2. projection registry は各 key を動画 authoring の用途へ分類する。
3. compiler は active な動画 fragment だけで provider prompt と review trace を生成する。
4. request / semantic review / provider 実行は同じ compiled payload を読む。

## Projection axes

各 rule は次を持つ。

- `authoring_relevance: required|conditional|none`
- `provider_projection: derive|may_surface|must_not_surface`
- `review_visibility: projection|review_only|none`
- `target_group`
- `transform`
- `semantic_checks`

初期 group は `start_state`, `primary_motion`, `camera_motion`, `environment_motion`, `emotional_change`, `end_state`, `continuity`, `constraints` とする。時代・時間帯は開始画像を再描写する情報ではなく、光・衣装・環境を変化させない continuity constraint として条件付きで使う。

## Compiler contract

`video_api_prompt_v1` は次を返す。

- provider-facing `prompt`
- provider / mode
- included and omitted fragments
- projection review contract
- `source_digest`
- exact prompt `sha256`

provider prompt には設計 key 名、ID、path、hash、narration、review instruction を含めない。空の optional group は出力しない。authoring source の自由文は主動作の候補であり、canonical motion contract があればそちらを優先する。

## Review symmetry

semantic review は raw motion source だけでなく、compiled provider prompt、active projection rule、compiler policy/hashを受け取る。reviewer は次を判定する。

- 開始フレームの可視状態から自然に動き出すか
- 一つの主動作に絞られているか
- camera と subject motion が競合しないか
- 宣言した end/handoff state に到達するか
- reveal、人物、重要物を発明していないか
- 時代、時間帯、人物、衣装、空間、光を壊していないか

## Compatibility

- canonical `cut_contract.motion_contract` を優先する。
- flat `video_generation.motion_contract` と legacy `scene_contract` alias は registry resolver で読む。
- legacy `motion_prompt` は authoring source として保持できるが、compiled payload がある場合の provider 送信は payload を正本とする。
