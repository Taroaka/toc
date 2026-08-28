# Requirements: Scene semantic review shift-left

## Goal

後段の `scene_set` semantic reviewer が初めて発見している因果、役割、reveal、時刻、場所、正典順序、handoff の矛盾を、scene authoring の入力契約と作成直後 preflight へ前倒しする。

最終 reviewer は削除せず、authoring と独立した contextless audit として残す。最終 reviewer の主責務は、構造的な取りこぼしの初回発見ではなく、機械判定できない意味品質と cross-scene の残存矛盾の確認にする。

## Problem statement

現行 frontend create は `scripts/toc-immersive-frontend-run.py::_build_script_and_manifest()` の単一 scene loop 内で、scene intent、scene event、cut coverage、cut contract を順次生成する。全 scene の cross-scene invariant を先に固定していないため、次の値が別々の heuristic から推論される。

- canonical event の scene / beat ownership
- participants と required roles
- artifact / information の reveal state
- time-of-day / location route と遷移 cue
- incoming / outgoing handoff の ownership
- source-specific non-replaceable elements
- causal turn と、その visible proof

その結果、schema と deterministic gate を通っても、後段 reviewer で次のような矛盾が見つかる。

- 一度 reveal した物を後続 scene で再び withheld とする
- helper / witness / community が必要なのに participants へ含めない
- 現 scene の出来事を前 scene の outgoing handoff として所有させる
- 時刻や場所が飛ぶのに経過・移動 cue がない
- canonical event が review-only prose にだけ存在し、ordered scene event から欠落する
- source-specific evidence が「手元」「床や道具の痕跡」のような generic fallback へ縮退する
- causal turn の説明と、画面上の action / result が一致しない

## Success criteria

- 新しい authoring agent が会話履歴を知らなくても、scene 作成前に同じ acceptance criteria、key、ownership rule、出力例を grounding readset から取得できる。
- 全 scene の `canonical event ownership / reveal ledger / role binding / time-location transition / handoff chain` を、個別 scene authoring より先に一つの machine-readable contract として固定する。
- 個別 scene author は、自 scene の contract slice と前後 handoff だけを入力にし、後段 reviewer の reason key に対応した作成条件を prompt で受け取る。
- cut materialization より前に、全 scene の deterministic authoring preflight が pass する。
- deterministic preflight は、少なくとも既存 Cinderella で観測した次の矛盾を provider review なしで検出する。
  - canonical event の欠落、重複、順序破壊、scene ownership の不一致
  - reveal state の逆行と、allowed reveal ownership の不一致
  - required role と participant / visible actor の closure 不足
  - adjacent scene の handoff anchor / owner / state の不一致
  - time/location discontinuity に必要な transition cue の欠落
  - non-replaceable element / source ref の欠落
- causal proof の説得力、story-specificity、価値増幅など、意味判定が必要な項目は authoring instruction と最終 semantic reviewer の双方が同じ criterion ID を参照する。
- 最終 contextless reviewer は authoring transcript や自己採点を信用せず、canonical artifact と frozen authoring contract だけで独立判定する。
- 最終 reviewer が deterministic-owned criterion を失敗させた場合は `shift_left_escape` として記録し、validator / fixture の欠陥として追跡できる。
- 新規 run では、既知の deterministic contradiction による producer repair round を開始しない。
- preflight はローカル処理であり、scene-set 全体に対する追加 provider turn を必須にしない。
- legacy run は marker 不在だけで破壊しない。現行 Cinderella に適用する場合は、p500 resume ではなく checkpoint 付き p400 scene-design rebuild を明示的に使える。
- contract と scene draft は、自由文の存在ではなく `event_id / beat_id / evidence_id / role_id / character_id / handoff_anchor_id / transition_cue_id / reveal_transition_id` の exact reference で結合される。
- authoring generation、contract、preflight、source artifact、criterion registry は digest で相互束縛され、どれかが変われば旧 preflight / review を無効化する。
- corrected Cinderella golden は scene-set semantic attempt 1回、producer repair 0回で通過し、known-bad deterministic fixture は semantic provider call 0回で停止する。

## Scope

- scene acceptance criteria の単一 registry
- scene-set authoring contract と artifact template
- scene-set planning と scene/cut materialization の二段階化
- deterministic preflight と report / state contract
- scene authoring prompt への acceptance contract projection
- `scene_set` semantic review pack / prompt の contract binding
- targeted producer repair routing と telemetry
- current Cinderella を同じ run のまま p400 から安全に再設計する migration path
- unit / integration / regression / performance tests

## Non-goals

- 最終 contextless semantic reviewer を廃止すること
- semantic quality を文字列 regex や schema success だけで合格扱いにすること
- reviewer と author を同じ context / transcript で自己承認させること
- 原作の主要イベント、意味、人物関係、結末を自動変更すること
- generic fallback phrase の禁止語リストだけで story-specificity を判定すること
- p500 resume skill に p400 artifact の暗黙変更を混ぜること
- 既存 run を無承認で一括 migration すること

## Decision rules

- comments は authoring guidance、machine-readable contract は実行正本、validator は構造・参照整合、semantic reviewer は意味品質を担当する。
- canonical artifact の主方式に Pydantic / JSON Schema を置かない。既存の Markdown 内 YAML、拡張可能な dict、legacy marker、cross-field validator と整合する plain Python validator を正本にする。
- Pydantic は将来の API request / response boundary または JSON export の検証に限って利用できる。
- deterministic に判定できる criterion は final reviewer まで先送りしない。
- semantic criterion は authoring prompt に明示するが、final reviewer の独立判定を省略しない。
- scene contract 自体に矛盾がある場合は、個別 scene prose を継ぎ足して回避せず、scene-set planner へ戻す。
- 原作価値または source event ownership の変更が必要な repair は human approval へ送る。
- scene-set contract を唯一の authoring root とし、`canonical_event_coverage_matrix`、scene draft、manifest は一方向 projection にする。
- p400 rebuild は active artifact を直接編集しながら進めない。generation staging を検証後、exclusive run lock と commit journal の下で publish する。

## Acceptance evidence

- known-bad Cinderella fixture が preflight で期待 reason key を返す
- corrected fixture が preflight を pass し、cut materialization へ進む
- final semantic reviewer pack が同じ contract digest と criterion registry version に束縛される
- preflight pass 後に deterministic-owned final finding が出た場合、escape telemetry が残る
- marker なし legacy fixture は互換経路で読める
- current Cinderella の p400 rebuild dry-run が preserve / replace / invalidate 対象を明示し、apply 前に plan token を要求する
