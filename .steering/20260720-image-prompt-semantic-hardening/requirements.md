# Requirements

## Goal

今後の frontend create で、scene 全体の出来事列や非描画概念を一枚の cut prompt に混入させず、reusable asset の人数・衣装・時間 variant を明示し、画像を実生成しない run でも semantic QA を必ず完了させる。

## Success criteria

- `materialize-only` は「media を生成しない」だけを意味し、`scene_set`, `scene_detail`, `cut_blueprint`, `asset_plan`, `image_prompt` の semantic review / repair を省略しない。
- semantic report が `pending` の run を正常な p650 到達として扱わない。
- 参照画像 bytes が未生成でも draft image prompt を意味レビューできる。一方、参照 hash 未解決の draft を provider-ready `frozen` と扱わない。
- cut prompt compiler は出来事列、未解決選択、制作 meta、壊れた結合文を provider prompt の前で拒否する。
- reference instruction は「参照画像の構図へ合わせる」と誤読させず、参照は identity / structure のみ、現在の cut plan を構図・状態の正本とする。
- character asset は individual / ensemble と人数を明示し、全件を「人物1人」に潰さない。
- character asset の衣装は役割・身分・状態を描画可能な appearance contract から作り、全役共通の「生活感のある衣装」を使わない。
- reusable asset の時間帯は `neutral_anchor|time_variant|state_variant` の明示契約で扱い、文中 keyword から推測しない。
- neutral character / object / location asset に scene 固有の朝・夜・月光を焼き込まない。time variant は時間帯と派生元を明示する。
- 過去の `output/シンデレラ_20260720_1611` は変更しない。

## Scope

- image prompt compiler と deterministic gate
- asset prompt contract / compiler / frontend materialization
- semantic review pack と frontend create の実行順
- p650 materialize-only validation
- canonical docs / templates / tests

## Out of scope

- 破棄予定の既存 Cinderella run の修復・再生成
- 生成済み画像そのものの視覚 QA
- 過去 run の migration
