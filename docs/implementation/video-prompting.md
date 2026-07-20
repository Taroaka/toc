# Video Prompt Projection / Compilation

動画の story / scene / cut 設計を、provider に渡す短い motion prompt へ安全に投影する契約を定義する。動画生成全体は [`docs/video-generation.md`](../video-generation.md)、Kling 固有の制約は [`workflow/playbooks/video-generation/kling.md`](../../workflow/playbooks/video-generation/kling.md) を参照する。

## 正本境界

story / scene / cut 設計と provider prompt は別物として扱う。

```text
story / scene / cut の canonical design
  -> video prompt projection registry
  -> compile_video_api_prompt_v1
  -> video_generation.api_prompt_payload
  -> review projection / semantic review
  -> provider API
```

- canonical design は、物語上の責務、event / reveal 境界、開始状態、主動作、終了状態、continuity を保持する
- projection registry は、各設計 key が authoring / provider / review のどこで必要かを分類する
- compiler は active な情報だけを provider-facing な断片へ変換する
- provider へ送る motion text の正本は、materialize 済み `api_prompt_payload.prompt`
- `prompt_authoring_source` は frontend の編集値または legacy 自由文を保持する compatibility input であり、canonical design を上書きする別正本ではない
- `motion_prompt` は legacy 入力として読めるが、新規 artifact では `api_prompt_payload.prompt` の read-only compatibility projection とする

`cut_function`、`target_beat`、event ID、reveal ID、path、hash、画像 prompt、narration、review instruction は設計・レビューには必要でも、provider prompt 本文へ出さない。

### 3 種類の identity

同じ文字列を複数の正本として扱わない。動画 prompt では次の identity を分ける。

- **authoring identity**: canonical story / scene / cut design と、canonical group が空のときだけ使う `prompt_authoring_source`。人または agent が直す入力であり、provider へ直接送らない
- **compiler identity**: `policy_version` / `compiler_version` / `projection_registry_version` と、正規化した全 compilation source の `source_digest`。同じ設計・設定・参照・実行 option から同じ payload を得たことを表す
- **persisted provider-request identity**: materialize 済み `api_prompt_payload.prompt` / `negative_prompt` / `sha256` / `provider_request_binding`。provider call が読む exact request の正本である

`motion_prompt` は persisted `prompt` の compatibility projection にできるが、authoring identity に戻して再解釈しない。`prompt` が同じでも `negative_prompt`、frame、reference bytes、model、duration、review-only event 境界が変われば compiler / provider-request identity は別物である。

## 入力の優先順位

compiler は canonical source を優先し、値がない場合だけ旧形式または自由文を fallback として使う。

1. `cut.cut_contract`
   - `first_frame_contract`
   - `motion_contract`
   - `continuity_contract`
   - `viewer_contract`
   - `source_event_contract`
2. flat `video_generation.motion_contract` / legacy `scene_contract`
3. `video_generation.prompt_authoring_source` / `source_motion_prompt` / legacy `motion_prompt`
4. 安全な最小動作 fallback

上位 source に値がある group へ、下位 source の競合値を継ぎ足さない。自由文は canonical motion を補う候補であって、cut の event 境界や終了状態を変更する権限を持たない。

## Projection Registry

code source of truth は `toc/video_prompt_projection_registry.py`、version は `video_prompt_projection_registry_v3`。

### 3 axes

各 rule は、次の 3 軸を必ず持つ。

| axis | 値 | 意味 |
|---|---|---|
| `authoring_relevance` | `required\|conditional\|none` | 動画設計時に必須か、条件付きか、対象外か |
| `provider_projection` | `derive\|may_surface\|must_not_surface` | provider 文へ変換するか、必要時だけ出せるか、絶対に出さないか |
| `review_visibility` | `projection\|review_only\|none` | projection trace として見せるか、review 根拠だけに使うか、review にも出さないか |

rule は併せて `source_keys`、`target_group`、`transform`、`semantic_checks` を持つ。provider に出さない rule は `exclusion_reason` を持つ。

### 8 groups

provider fragment の順序は固定する。空の optional group は出力しない。

| order | group | 内容 |
|---:|---|---|
| 1 | `start_state` | 承認済み first frame から自然に動き出すための可視開始状態 |
| 2 | `primary_motion` | clip が担う一つの中心動作 |
| 3 | `camera_motion` | 主動作と競合しない camera 移動 |
| 4 | `environment_motion` | 開始画面に存在する霧、風、水、光などの小さな動き |
| 5 | `emotional_change` | 表情、姿勢、視線、timing で見える小さな感情変化 |
| 6 | `end_state` | clip の可視終了状態または handoff。last frame があれば到達境界 |
| 7 | `continuity` | 人物、衣装、小道具、空間、方向、光、時代、時間帯の維持 |
| 8 | `constraints` | 新規人物・重要物・reveal・別 shot 化など高リスクな追加の禁止 |

registry 出力は `groups`、`active_rules`、`inactive_rules`、`excluded`、`review_only_sources`、`shadowed_sources` を持つ。`must_not_surface / review_only` の source が存在するとき、`review_only_sources[]` は `source_key` だけでなく正規化前の **exact `value`** を保持する。この exact value は `source_digest` と semantic reviewer の入力へ含める一方、provider prompt 本文へは出さない。reviewer は raw source の自己申告ではなく、この projection trace と compiled prompt の対応を検査する。

自由文 authoring source は compiler が一度だけ group 別に parse し、`compiler_normalized.authoring_source.<group>` として registry へ渡す。たとえば `camera:` 行を `camera_motion` に採用した場合、raw 自由文を同時に `primary_motion` として active trace へ残さない。`authoring_source_normalization` はこの正規化前後の対応を review 用に保持する。

### 設計情報の代表的な分類

- `cut_contract.motion_contract.motion_brief` は `primary_motion` へ `derive`
- `cut_contract.motion_contract.camera_motion` は `camera_motion` へ条件付き `derive`
- `cut_contract.viewer_contract.target_beat` と event / reveal ID は `review_only` かつ `must_not_surface`
- image prompt と narration prose は動画 motion の authoring source にせず、`review_only` かつ `must_not_surface`
- `video_metadata.time` と `scene.time_of_day` は `continuity` へ条件付き `derive`
- `scene.time_of_day_visual_basis` は daypart 設計を検査する `review_only / must_not_surface`。provider prose は canonical `scene.time_of_day` から一度だけ作る
- `scene.location_mode` / `scene.location_sequence` / `scene.location_segments` は scene routing の `review_only / must_not_surface`。一つの video clip は担当 cut の一場所だけを使う
- `video_generation.references` は provider binding path として `review_only / must_not_surface`、`video_generation.reference_roles` は path を出さず参照順の意味だけを `continuity` へ投影する
- `cut_contract.motion_contract.allowed_new_reveal_elements` は、主動作で新しく現れてよい具体要素だけを `constraints` へ条件付き `derive` する正の allowlist
- `cut_contract.source_event_contract.allowed_reveal_info_ids` と upstream の `use_next_cut_first_frame_as_last_frame` は review / boundary 解決用で provider prose へ出さない。後者は解決後の `provider_request_binding.last_frame` としてのみ効く

## Compiler Contract

`compile_video_api_prompt_v1` は deterministic に `video_api_prompt_v1` payload を返す。compiler version は `conditional_video_prompt_compiler_v3`、IR schema は `video_prompt_ir_v2`。

```yaml
api_prompt_payload:
  policy_version: "video_api_prompt_v1"
  compiler_version: "conditional_video_prompt_compiler_v3"
  projection_registry_version: "video_prompt_projection_registry_v3"
  provider: "kling_3_0"
  mode: "text_to_video|image_to_video|first_last_frame|reference_to_video"
  provider_policy:
    one_clip_one_intent: true
    max_camera_instructions: 2
    single_continuous_shot: true
    first_last_frame_boundary: false
    multimodal_reference: false
    negative_prompt_mode: "separate|inline"
  provider_request_binding:
    duration_seconds: 8
    quality: "1080p"
    aspect_ratio: "16:9"
    first_frame: "assets/scenes/scene01_cut01.png"
    last_frame: ""
    references: []
    reference_roles: []
    execution_options:
      backend: "kling"
      model: "kling-3.0"
      extra_payload: {}
      reference_content_sha256:
        assets/scenes/scene01_cut01.png: "<sha256-of-reference-bytes>"
  prompt: "<exact provider-facing motion prompt>"
  negative_prompt: "<compiled high-risk constraints>"
  source_digest: "<sha256-of-normalized-compilation-source>"
  sha256: "<sha256-of-exact-prompt-utf8>"
  included_fragments:
    - group: "primary_motion"
      text: "<provider-facing sentence>"
  omitted_groups: []
  quality_issues: []
  projection_review_contract:
    registry_version: "video_prompt_projection_registry_v3"
    group_order: [start_state, primary_motion, camera_motion, environment_motion, emotional_change, end_state, continuity, constraints]
    groups: {}
    active_rules: []
    inactive_rules: []
    excluded: []
    review_only_sources: []
    shadowed_sources: []
    provider: "kling_3_0"
    mode: "image_to_video"
  video_prompt_ir:
    schema_version: "video_prompt_ir_v2"
    provider: "kling_3_0"
    mode: "image_to_video"
    dependencies:
      story_time: ""
      time_of_day: "夜明け"
      has_first_frame: true
      has_last_frame: false
      duration_seconds: 8
      reference_roles: []
      required_groups: [start_state, primary_motion, continuity, constraints]
    included_fragments: []
    omitted_groups: []
    quality_issues: []
```

### `prompt` と metadata の境界

`api_prompt_payload.prompt` は、provider へ渡す exact motion text である。次は本文へ出さない。

- `cut_contract` などの key 名と `start_state` などの raw group 名
- scene / cut / event / asset の内部 ID
- file path、policy / compiler version、digest、hash
- image prompt、narration / TTS text、review instruction
- `target_beat` や `cut_function` のような制作上の意味ラベル

`review_only_sources[].value` は上記の情報を reviewer と digest に exact binding するための metadata であり、`prompt` へ転載しない。daypart の visual basis、複数場所 route / segment、cut の物語上の責務、event / reveal 境界、image prompt、narration、参照 path はこの経路で検査する。

これらは `video_prompt_ir` または `projection_review_contract` で追跡する。設計を直すときは provider prompt を直接編集せず、上流設計を直して再 compile / 再 materialize する。

### hash の役割

- `sha256`: `prompt` の UTF-8 bytes に対する exact SHA-256。provider へ送る文字列の同一性を検証する
- `source_digest`: policy / compiler / provider / mode / exact negative prompt / temporal continuity / canonical design / authoring fallback / projection 結果に加え、`provider_request_binding` の duration / quality / aspect ratio / first-last frame / ordered references / execution options を正規化した compilation source の SHA-256。設計 revision と provider request の同一性を検証する

materializer は first / last / references のうち現在読める file bytes も `reference_content_sha256` として execution options に含める。同じ path の画像を差し替えても `source_digest` が変わる。CLI は last-frame 有効/無効、reference strip を含む実効値を先に解決してから materialize し、review 後に別の frame 構成へ書き換えない。前clipから新しいchain frameを抽出する場合は、その生成後に次clipを再materialize・再review・再approveする。provider実行中の動的chain flagは使わない。

`provider_request_binding.references` は順序付き path identity、`provider_request_binding.reference_roles` は同じ順序の意味 binding、`execution_options.reference_content_sha256` は materialize 時点で存在する first / last / auxiliary reference の file bytes identity である。実行時は path、role、hash をすべて照合する。server worker は承認済み bytes を private snapshot へ複写して再検証し、その snapshot を provider に渡す。materialize 時点でまだ存在しない chain output は勝手な placeholder hash を作らず、producer / path binding を保持し、実在 bytes を束縛できる段階で再 materialize / 再承認する。

review-only の event 境界が変わり provider text が同じ場合、`sha256` は同じでも `source_digest` は変わり得る。実行可否は prompt hash だけで判断しない。

## Temporal Continuity

- `video_manifest.md.video_metadata.time` は物語世界の歴史的時代
- `video_manifest.md.scenes[].time_of_day` は scene の一日の時間帯
- `video_manifest.md.scenes[].time_of_day_visual_basis` は `time_of_day` から導いた光源・明るさ・影・色温度の review evidence であり、第二の authoring source ではない
- どちらも動画中に新しく描き直す対象ではなく、開始状態から終了状態まで変えない `continuity` constraint
- `time` から time-lapse、衣装替え、建築変更を発明しない
- `time_of_day` から日の出・日没・再照明を発明しない
- 空値では placeholder fragment を作らない

時代または時間帯そのものが物語上変化する cut は、単なる continuity metadata の書き換えで表現せず、canonical event / motion / end-state 設計として明示する。

## Provider Mode / Boundary

- first frame なし: `text_to_video`
- first frame あり: `image_to_video`
- first frame と last frame あり: `first_last_frame`
- first / last frame なし、`references[]` あり: `reference_to_video`

first frame は departure boundary である。人物、構図、物の位置、光を開始状態として扱い、参照にない人物・重要物・reveal を足さない。last frame は arrival boundary であり、別 shot の素材として挿入せず、一つの連続運動で到達する。途中の fade、cut、dissolve、視点 jump で境界を偽装しない。

### Exact-obligation reveal / next-frame boundary

開始画像から主動作によって新しい人物状態・小道具・舞台要素を出す cut は、blanket な「追加禁止」を消さず、該当 cut 責務の `beat_overrides.<function>.obligation_overrides.<obligation_id>` にだけ次を置く。

- `allowed_new_reveal_elements[]`: provider 画面へ現れてよい具体要素
- `allowed_reveal_info_ids[]`: canonical reveal inventory のうち当該 cut だけで解禁する内部情報 ID
- `use_next_cut_first_frame_as_last_frame`: current clip の arrival boundary を next cut の approved first-frame image に固定する boolean

segment root や function rootへ置いて sibling obligation を一括許可しない。compiler / materializer は次を fail closed で検証する。

- `allowed_new_reveal_elements` は非空・一意、最大8件
- 各許可要素が exact obligation の `motion_brief` または `motion_end_state` に文字列として接地する
- 許可要素と `must_not_add` が交差しない
- `allowed_reveal_info_ids` が canonical reveal inventory に存在し、当該 cut の forbidden reveal からだけ除外される
- next-frame binding は次 cut が存在し、同じ location で、current end state と許可済み reveal が next first-frame contract に一致する
- next first-frame image が approved/current で、その path・bytes hash が current request の last-frame binding に含まれる

`use_next_cut_first_frame_as_last_frame` は reveal authorization ではない。新しい画面要素には `allowed_new_reveal_elements`、新しい物語情報には `allowed_reveal_info_ids` が別途必要である。複数 cut render unit は source cut の allowlist を自動合成せず、unit-level の明示的な reveal authorization がなければ拒否する。

allowlist が非空なら positive prompt の `constraints` に「主動作によって新しく現れてよいもの」と許可要素を出し、その直後に「承認済み要素以外」の追加禁止を置く。`negative_prompt_mode: separate` では正の allowlist 文と許可要素名を separate `negative_prompt` から除外し、残余禁止だけを送る。`negative_prompt_mode: inline` では保存 `negative_prompt` は空で、allowlist と残余禁止の両方を positive constraints に保持する。内部 `allowed_reveal_info_ids` はどちらの provider prose にも出さない。

Kling 系では追加で次を固定する。

- 1 clip 1 intent
- camera 指示は最大 2 つ
- single continuous shot
- first / last boundary を保つ

provider のモデル機能と、ToC adapter が実際に型付きで送信できる入力は分けて扱う。現在の Kling adapter が送信できる画像境界は first / last frame だけであり、`references[]` の auxiliary image は送信しない。Kling target に auxiliary reference が残ったまま approval / 実行へ進むことはエラーとし、黙って破棄しない。複数画像 reference が必要な target は、型付き `reference_images` を実装済みの Seedance を選ぶ。

`image_generation.references[]` は承認済み first frame を構成する画像prompt入力であり、動画providerの補助入力ではない。動画側へ渡す ordered references は `video_generation.references[]` に明示したものだけとし、画像生成用参照を暗黙継承しない。

Seedance では first-frame、first-and-last-frame、multimodal reference を別 mode とし、frame boundary と `references[]` を同じ request に混在させない。`reference_to_video` は reference 対応 I2V model を選び、`provider_request_binding.first_frame` / `last_frame` を空に保つ。複数参照のうちどれを開始状態として使うかは prompt 内で指定できるが、strict な first-frame 一致保証とは扱わない。

### Ordered reference role binding

storyboard-backed render unit は sibling `video_input_contract` に ordered reference と役割を一緒に固定する。

```yaml
video_input_contract:
  schema_version: "render_unit_video_input_v1"
  input_mode: "reference_images"
  required_references:
    - "<first source cut full-frame>"
    - "<ordered storyboard>"
  reference_roles:
    - image_index: 1
      role: "start_state_visual_anchor"
    - image_index: 2
      role: "ordered_storyboard_sequence_guide"
```

- `reference_roles[]` の件数は `required_references[]` と一致させる
- `image_index` は 1 起点で連番・一意・配列順と一致させる
- role は `start_state_visual_anchor | ordered_storyboard_sequence_guide` のみを許可する
- canonical storyboard unit では image 1 を開始状態 anchor、image 2 を順序付き storyboard guide に exact binding する
- materializer はこの配列を失わず compiler の `reference_roles` へ渡し、`provider_request_binding.reference_roles`、`video_prompt_ir.dependencies.reference_roles`、`source_digest` に同値を保存する
- provider prose には `参照画像1は開始状態の基準として使う` のような role 指示だけを出し、file path、asset ID、hash は出さない

件数、index、role、ordered reference との対応が一致しない target は materialize / approval / provider execution 前に拒否する。role 配列だけを並べ替えた場合も `source_digest` が変わるため再 review / 再承認が必要になる。

duration と reference 数は共通上限ではなく、承認対象に束縛した provider / model / input mode の capability で検査する。現在の Seedance 1.0 reference-image mode は 2–12 秒、ordered references 1–4 枚である。storyboard unit の分割、materialization、approval、CLI/server execution はすべて同じ capability 判定を使い、13–60 秒を「共通60秒以内」という理由で承認しない。

negative channel も adapter 能力に合わせる。Kling 等の separate channel 対応 provider は `negative_prompt_mode: separate` とし、exact `negative_prompt` を送る。現在の Seedance adapter は separate negative field を持たないため `negative_prompt_mode: inline` とし、追加禁止を compiled positive prompt の `constraints` fragment へ入れ、保存する `negative_prompt` は空文字にする。承認した禁止指示を未送信 field にだけ残してはならない。

## Blocking Motion Quality Issues

video compiler v3 は syntax が成立しても動画指示として確定していない状態を `quality_issues[]` に出す。各 item は `code`、`blocking: true`、`group`、`message`、`value` を持ち、`api_prompt_payload` と `video_prompt_ir` の双方へ同じ値を保存する。

| code | 意味 | 修正先 |
|---|---|---|
| `video_motion_generated_fallback` | canonical source から主動作を解決できず compiler が最小動作を補った | `motion_contract.motion_brief` / `subject_motion` |
| `video_motion_unresolved_alternative` | `または` / `もしくは` / `あるいは` / `or` が残り、画面上の状態が一つに確定していない | 該当 start / motion / environment / emotion / end field |
| `video_motion_abstract_primary` | 主動作が「変化を見せる」等の抽象ラベルで、観察可能な人物・物の動作になっていない | `motion_contract.motion_brief` |
| `video_motion_abstract_end_state` | 終了状態が「変化点」「物証」等の抽象ラベルで、静止画として確認できない | `motion_contract.end_state` / `end_frame_brief` |
| `video_motion_duplicate_environment` | environment motion が primary motion の複製で、補助情報になっていない | `motion_contract.environment_motion` |
| `video_motion_duplicate_emotion` | emotional change が primary motion の複製で、可視感情差分になっていない | `motion_contract.emotional_change` |

blocking issue が一件でもある target は semantic review で合格にせず、canonical field を修正して再 compile / 再 materialize する。fallback 文や compiled prompt の直接編集で issue を隠さない。

scene composite review は cut 単体の `quality_issues` に加え、同一 scene 内の primary motion と physical end state を比較する。別の `coverage_obligation_id` が同じ動作・同じ終了配置を反復する場合は、object proof、spatial transition、deadline、reaction、terminal resolution など cut 固有の責務へ投影し直す。修正対象は `cut_contract.motion_contract`、`continuity_contract`、`video_input_contract.reference_roles` であり、compiled prompt や `video_generation_requests.md` を直接編集しない。

## Render Unit Contract

`scenes[].render_units[]` は複数 cut を一つの provider clip に束ねる任意の最終 render 単位である。存在する scene では cut clip と render unit clip を二重に正本化しない。

- `unit_id` は scene 内で一意、`source_cut_ids[]` は非空で canonical cut 順を保つ
- active cut は scene 内のいずれか一つの render unit に exactly once 所属し、重複・欠落・deleted cut 参照を許さない
- unit の `video_generation.duration_seconds` は `source_cut_ids[]` の cut duration 合計と一致させる。provider / model / input mode の duration 上限を超える前に unit を分割する（現在の Seedance 1.0 reference-image mode は最大12秒）
- 1 cut unit の effective contract は source cut contract を exact 継承する
- 複数 cut unit は、先頭 cut の `first_frame_contract`、末尾 cut の `motion_contract.end_state` / `end_frame_brief`、全 source cut の continuity / `must_not_add` の和集合を境界 contract とする
- 個別 cut の主動作を連結して一つの長い prompt にしない。複数 cut unit は unit-level `cut_contract.motion_contract` または `prompt_authoring_source` に、clip 全体を代表する **一つ**の primary motion を明示する
- unit に explicit `cut_contract` がある場合は derived boundary contract を補完元とし、同じ group の explicit 値を優先する

`source_cut_ids[]` と source cut contract の ordered set は provider prompt 本文へ出さず、`review_only_dependencies` として `source_digest` に束縛する。したがって prompt text が偶然同じでも source cut の順序・event 境界・continuity が変われば再 review が必要になる。

## Materialization / Execution Gate

frontend/server、CLI、scene storyboard の全経路は同じ compiler を使い、provider 実行前に target の `video_generation.api_prompt_payload` と `video_generation_requests.md` を materialize する。責務は次のように分ける。

- frontend/server materializer は manifest payload と review artifact を保存し、semantic review が current と確認できるまで per-item state を `pending` にする。明示的な `approve_for_generation: true` の操作だけが approval identity を保存できる
- CLI の materialize-only 経路も compiler output を manifest と review artifact へ保存し、対象 item を `pending` にする。CLI は materialize や通常実行を approval の代わりにせず、未承認 item を自動承認しない
- CLI / server の provider execution は保存済み payload と current 再 compile、review section、per-item approval identity を照合する。再 compile 結果は stale 判定用であり、送信 prompt を editable source から作り直すためには使わない
- scene storyboard 作成は render unit payload / request を保存して `pending` にし、同じ review / approval gate を通す

scene storyboard 経路では、先頭 cut の full-frame image と multi-panel storyboard を ordered `references[]` として分離し、Seedance の `reference_to_video` target として materialize する。frame-boundary mode と reference mode は混在させない。prompt は先頭 full-frame image を開始状態、storyboard を順序・連続性の参考として指示するが、storyboard 自体を literal first frame にして「分割画面禁止」と同時要求してはならない。

materialization では少なくとも次を保存する。

- exact `prompt`
- `policy_version` / `compiler_version` / `projection_registry_version`
- `source_digest` / prompt `sha256`
- `video_prompt_ir` / `projection_review_contract`（`review_only_sources[].value` を含む）
- `quality_issues[]`。blocking issue がある target は approval へ進めない
- provider / mode / duration / tool / quality / aspect ratio
- first frame / last frame / ordered references / ordered `reference_roles` と、materialize 時点で読める各 reference bytes の hash
- provider mode に応じた exact `negative_prompt` とその hash。`inline` mode では空文字とその hash
- model / backend / provider extra JSON などの execution options
- `video_generation_requests.md` の target ごとの exact section hash

`video_generation_requests.md` は positive prompt を exact `video_prompt` fence、negative prompt を exact `negative_prompt` fence に保存する。各 section の `negative_prompt_sha256` は後者の UTF-8 hash であり、`request_section_sha256` は heading、metadata、両 fence を含む materializer が書いた target section の exact bytes hash である。空の negative prompt でも fence と空文字 hash を省略しない。

materialize しただけの target は `pending` であり生成できない。明示的な生成操作は create request に `approve_for_generation: true` を付け、target ごとに次の approval identity と audit metadata を `state.txt` へ保存する。

approval identity:

- `review.video_prompt.item.<item_id>.status=approved`
- `request_section_sha256`
- prompt `sha256`
- `source_digest`

audit metadata:

- `approved_by` / `approved_at`

`approved_by` / `approved_at` は誰がいつ操作したかの監査情報であり、request bytes の identity ではない。これらが存在しても `status` と 3 つの identity binding が current request と一致しなければ承認にはならない。negative prompt、provider request binding、reference content hash は `source_digest` と request section hash の双方を通じて approval に束縛される。

一部 target だけを更新した場合は run 全体を承認済みとは扱わず、`partially_approved_for_generation` とする。実行可否は run-level の表示だけでなく、この per-item binding で判定する。

生成 API は保存済み payload だけを provider request へ使い、送信前に次を照合する。

1. target と materialized payload が存在する
2. policy / compiler / projection registry version が current である
3. `sha256` が exact saved prompt と一致する
4. current canonical design から再 compile した `prompt` / `sha256` / `source_digest` が保存値と一致する
5. tool / duration / quality / aspect ratio / first / last / references / `reference_roles` が materialize 時の設定と一致する
6. exact negative prompt、model、provider execution options が materialize 時の値と一致する
7. `video_generation_requests.md` の target section hash と per-item approval binding が一致する
8. review projection の exact `video_prompt` fence と保存 payload が一致する

未 materialize、pending / missing approval、request artifact 改変、hash mismatch、design digest drift、setting / reference bytes / execution option drift は stale request として拒否し、再 materialize を要求する。worker 開始後に editable draft や環境変数から provider request を再構成してはならない。provider extra JSON は prompt、model、duration、ratio、resolution、frame、negative prompt などの予約 field を上書きできない。

request artifact の canonical fence は `video_prompt` とする。旧 CLI artifact の `api_prompt` fence は読み込み互換だけ残し、新規書き出しでは使わない。

## Review Contract

semantic reviewer は provider prompt だけでなく `projection_review_contract` と `video_prompt_ir` を読む。少なくとも次を判定する。

- 承認済み開始状態から自然に動き出す
- primary motion が一つで、cut の担当 event 境界を越えない
- camera と subject / environment motion が競合しない
- end / handoff state または last frame に到達する
- 人物、重要物、reveal、別 shot を発明しない
- 人物、衣装、空間方向、光、時代、時間帯を drift させない
- active group が exactly one の非空 fragment と provider prompt trace を持つ
- `must_not_surface` の key / ID / prose が provider prompt に漏れていない
- `review_only_sources[].value` の exact daypart basis、route / segment、cut responsibility、event / reveal 境界と compiled motion が矛盾しない
- `quality_issues[]` に blocking item が残っていない
- ordered reference と `reference_roles` が一対一で、provider prose は role だけを説明し path / ID / hash を含まない

current version の materialized payload がある場合、semantic pack はその exact payload をレビューに渡す。ただし同時に current canonical design から再 compile し、prompt / negative prompt / `sha256` / `source_digest` / `provider_request_binding` が一致しなければ pack 作成を stale error で止める。保存済み `motion_prompt` を再び authoring prose として解釈しない。

## Compatibility / Extension Rule

- legacy `scene_contract`、flat `video_generation.motion_contract`、自由文 `motion_prompt` は canonical 値がない場合だけ読む
- compiled payload が存在する場合、legacy field を provider 送信正本として使わない
- compile / gate failure 時に自由文へ暗黙 fallback しない
- 新しい story / scene / cut / video design key を追加するときは、同じ変更で registry rule、compiler projection、tests、semantic reviewer の projection contract を更新する
- provider に出さない key も `authoring_relevance` / `provider_projection` / `review_visibility` と `exclusion_reason` を登録する
