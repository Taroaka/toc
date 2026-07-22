# Kling 3.0 Video Prompt Policy

ToC で `kling_3_0` / `kling_3_0_omni` を使うときの provider 固有 policy を定義する。動画 prompt の projection / compiler 正本は [`docs/implementation/video-prompting.md`](../../../docs/implementation/video-prompting.md)、動画生成全体は [`docs/video-generation.md`](../../../docs/video-generation.md) を参照する。

本書は canonical story / scene / cut design を置き換えない。Kling に渡す prompt を手書きで別正本化せず、canonical design を共通 compiler へ通した結果に Kling policy を適用する。

## 適用範囲

- `video_generation.tool: "kling_3_0"`
- `video_generation.tool: "kling_3_0_omni"`
- `cut_contract.first_frame_contract`
- `cut_contract.motion_contract`
- `cut_contract.continuity_contract`
- `video_generation.prompt_authoring_source`（frontend / legacy fallback）
- `video_generation.api_prompt_payload.prompt`（exact provider-facing motion text）
- first / last frame、Kling 向け continuity / constraints

`video_generation.prompt` を新しい正本 field として作らない。legacy `motion_prompt` は読み込み互換として扱えるが、materialized payload がある場合の送信正本は `api_prompt_payload.prompt` である。

現在の ToC Kling adapter は first / last frame だけを画像入力として送る。Kling 3.0 Omni 製品自体の Elements / multi-image 機能と、未実装の local `references[]` 転送を同一視しない。Kling target の auxiliary `references[]` と対応する `video_input_contract.reference_roles[]` は approval / provider 実行前に拒否し、ordered reference role binding が必要なら Seedance を選ぶ。

Kling target の payload `mode` は `text_to_video | image_to_video | first_last_frame` のいずれかとし、`reference_to_video` と非空 `references[]` は拒否する。

## ToC での位置づけ

- [`docs/video-generation.md`](../../../docs/video-generation.md)
  - 動画生成全般の stage / quality 原則
- [`docs/implementation/video-prompting.md`](../../../docs/implementation/video-prompting.md)
  - registry、compiler、IR、hash、materialization / stale gate
- 本書
  - Kling 固有の 1 clip 1 intent、camera、連続 shot、boundary policy
- `docs/vendor/kling/`
  - API / integration / billing の補助情報

`video_generation.tool` が Kling 系なら、authoring / review agent は汎用正本に加えて本書を読む。Kling 以外の provider へ本書の上限値を無条件適用しない。

## Canonical Design と Provider Prompt の境界

```text
cut_contract + first/last frame + continuity + settings
  -> video_prompt_projection_registry_v5
  -> compile_video_api_prompt_v1
  -> video_api_prompt_v1
  -> Kling API
```

- `cut_function`、`target_beat`、event / reveal ID は設計・review 用で、Kling prompt 本文へ出さない
- image prompt と narration / TTS prose を motion 指示として複製しない
- daypart basis、scene route / segments、cut responsibility、event / reveal 境界、reference path の exact value は `review_only_sources` と `source_digest` に残すが、Kling prompt 本文へ出さない
- `prompt_authoring_source` は自由入力の候補であり、canonical `motion_contract` と競合するときは canonical 値を優先する
- `motion_attention_target` は upstream cut authoring 用で、現行 video registry / compiler は独立 projection source / trace / provider fragment にしない。cut contract に保持された値は normalized design source として `source_digest` を変え得る。必要な対象指向は `motion_brief`、`emotional_change`、`end_state` に具体化する
- render unit の 1-cut effective contract は source contract を exact 継承する。explicit field の省略 / 空値は no-op とするが、非空の指定値が対応する source value と異なる場合は拒否し、出力を変更しない。multi-cut の explicit reveal allowlist は source cut 順に stable dedupe した reveal union と normalized member set が exact 一致しなければならず、出力順を stable source order に正規化する。欠落も superset による新 reveal の発明も拒否する
- provider へ渡す prompt を直したい場合は upstream design を直し、再 compile / 再 materialize する

## Kling の必須 Policy

### 1 clip 1 intent

- 1 clip の中心動作は一つにする
- 主動作は `1つの感情変化` または `1つの空間アクション` に寄せる
- 「振り向く、走る、爆発する、群衆が現れる」のような event 列を一つの clip に詰めない
- `その後` / `続いて` / `次に` で第二の大動作が必要なら cut を分ける

3秒前後の shot は authoring 時の分割目安であり、実際に送る duration は target の materialized `duration_seconds` を正とする。duration を伸ばすために intent を追加しない。

### Camera は最大2指示

- camera 指示は 1 つ、必要でも互換性のある 2 つまで
- 例: `胸の高さを保つ + 緩やかに寄る`
- 主動作が感情変化なら camera を安定させる
- 空間移動が主動作なら細かな人物演技を重ねすぎない
- 急旋回、複数方向への連続 pan / tilt / crane、視点 jump を避ける

### Single continuous shot

- clip 内で fade、暗転、dissolve、montage、別 shot への切替を行わない
- camera transition を編集点の代わりに使わない
- prompt が複数 shot を必要とするなら canonical cut / render unit を分ける

### First / last boundary

- first frame は departure boundary
  - 人物、構図、物の位置、光を開始状態として保つ
  - 参照にない人物、重要物、建築、reveal を追加しない
- last frame は arrival boundary
  - 一つの自然な運動で到達する
  - last frame を別 shot として挿入しない
  - fade / cut で到達を偽装しない

`beat_overrides.<function>.obligation_overrides.<obligation_id>.use_next_cut_first_frame_as_last_frame: true` を使う場合、次 cut が存在し、current `motion_end_state` と許可済み reveal が next first-frame contract と exact match しなければならない。同一 location ではその一致を必須とし、cross-location はさらに exact destination が `scene.location_sequence[]` と current obligation の `allowed_new_reveal_elements[]` の双方にある場合だけ許可する。next image は approved/current であることを検証し、materializer はその path と bytes hash を current Kling request の exact `last_frame` binding に含める。境界 flag だけで新しい reveal を許可してはならない。

## Canonical Motion Authoring

Kling 用 shot card の `タイトル / サブジェクト / カメラ / アクション / ボイス` は、次の canonical 契約へ落とす。

| shot card | canonical target | provider への扱い |
|---|---|---|
| タイトル | `viewer_contract` / review note | review-only。本文へ出さない |
| サブジェクト | first / last frame / visible start state | 開始状態と continuity へ必要分だけ投影。auxiliary reference は現在の adapter では禁止 |
| カメラ | `motion_contract.camera_motion` | `camera_motion` group。最大2指示 |
| アクション | `motion_contract.motion_brief` | `primary_motion` group。一つだけ |
| ボイス | narration / audio contract | motion prompt へ複製しない |

推奨 canonical 例:

```yaml
cut_contract:
  first_frame_contract:
    first_frame_brief: "侍が雨上がりの石畳で、まだ振り向く前に息を整えている"
    visible_start_state:
      character_state: "短い黒髪、紺の外套、左頬の細い傷"
      prop_state: "刀は同じ鞘に収まっている"
      spatial_state: "侍は路地の奥へ背を向けて立つ"
  motion_contract:
    motion_brief: "侍が息を整え、ゆっくり一度だけ振り向く"
    camera_motion: "胸の高さを保って緩やかに寄る"
    environment_motion: "軒先から雨粒が落ち、薄い霧だけが流れる"
    emotional_change: "警戒から決意へ視線が定まる"
    end_state: "侍の横顔と視線が路地の奥へ定まる"
    must_not_add: ["新しい人物", "抜刀", "別の場所"]
  continuity_contract:
    carry_forward_to_next_cut:
      - "顔、傷、髪、紺の外套を変えない"
      - "刀の鞘と路地の奥行きを変えない"
      - "雨上がりの反射と光源方向を変えない"

video_generation:
  tool: "kling_3_0"
  first_frame: "assets/scenes/example_start.png"
  last_frame: ""
  duration_seconds: 5
  prompt_authoring_source: "侍が一度だけ振り向く。胸の高さから緩やかに寄り、雨上がりの路地を保つ。"
```

`prompt_authoring_source` は自然文の fallback とする。`cut_function:`、`target_beat:`、`source_event_beat_id:` のような internal label を入れた自由文を provider prompt の原稿として扱わない。

## Compiled Provider Prompt

compiler は active な 8 groups だけを固定順で自然文化する。次は出力イメージであり、実行時の exact string は materialized `api_prompt_payload.prompt` を読む。

```text
[開始状態]
入力画像に写る人物、構図、物の位置、光を開始状態として保つ
侍が雨上がりの石畳で、まだ振り向く前に息を整えている

[主動作]
侍が息を整え、ゆっくり一度だけ振り向く。

[カメラ]
胸の高さを保って緩やかに寄る。

[環境の動き]
軒先から雨粒が落ち、薄い霧だけが流れる。

[感情の変化]
警戒から決意へ視線が定まる。

[終了状態]
侍の横顔と視線が路地の奥へ定まる

[維持条件]
顔、傷、髪、紺の外套を変えない
刀の鞘と路地の奥行きを変えない
雨上がりの反射と光源方向を変えない

[禁止]
追加しないものは、新しい人物、抜刀、別の場所
主動作は一つに絞り、単一の連続ショットとして見せる。急なcamera回転や視点ジャンプを行わず、別ショットへ切り替えない
```

provider prompt 例に raw key / ID / path / hash / narration / image prompt を混ぜない。実 path、hash、projection trace は payload metadata に残す。

compiler v5 が返す `quality_issues[]` は syntax warning ではなく blocking review input である。`video_motion_generated_fallback`、`video_motion_unresolved_alternative`、`video_motion_abstract_primary`、`video_motion_abstract_end_state`、`video_motion_duplicate_environment`、`video_motion_duplicate_emotion`、`video_motion_sequential_overview` が一件でもあれば、Kling 実行へ進めず canonical motion field を具体化して再 compile する。

## Temporal Continuity

- `video_metadata.time` は歴史的時代を変えないための continuity
- `scene.time_of_day` は空の明るさ、自然光 / 人工光、影、色温度を変えないための continuity
- どちらも clip 内で再描画するイベントではない
- `夜明け` だからといって日の出の time-lapse を足さない
- 歴史的時代から衣装替え、建築変化、技術変化を足さない

時間の変化そのものが story event なら、metadata の上書きではなく canonical motion / end state として設計する。

## Appearance / Motion / Voice の分離

- appearance
  - first frame
  - character / object / location reference
  - asset bible
- motion
  - `motion_contract` と必要な video reference
- voice
  - narration / dialogue / lip-sync contract

同じ人物や舞台を pure text だけで再現しようとせず、reference-first を基本にする。speech-heavy shot の読みは audio contract 側で管理し、難読漢字や固有名詞は必要に応じてかなへ寄せる。音声文字列を video motion prompt へ貼り付けない。

## Negative / Constraints

禁止事項は高リスクなものに絞る。

- 開始画像にない人物、重要物、建築、reveal
- 顔崩れ、手指崩れ、不自然な四肢
- 画面内テキスト、字幕、ロゴ、ウォーターマーク
- 急な camera 回転、視点 jump
- fade、暗転、dissolve、別 shot 化

禁止文を増やして intent がぼやける場合は、prompt を長くする前に shot の責務を切り直す。

開始画像にない要素を主動作で出す必要がある場合だけ、exact `beat_overrides.<function>.obligation_overrides.<obligation_id>` entry に次を置く。

- `location`: cut の departure location。exact `scene.location_sequence[]` 内だけ
- `first_frame_character_asset_overrides` / `first_frame_excluded_object_ids[]`: 開始側の人物 variant / object 除外
- `allowed_new_reveal_elements[]`: 最大8件の具体的な画面要素。すべて `motion_brief` または `motion_end_state` に現れ、`must_not_add` と交差しないこと
- `allowed_reveal_info_ids[]`: canonical reveal inventory に存在する、この cut だけの内部情報 ID。Kling prompt には出さないこと

変身後の人物参照、小道具、遷移先場所は開始画像へ先回りさせない。開始側は `first_frame_character_asset_overrides` / `first_frame_excluded_object_ids[]` / cut-local `location` で固定し、cut-local `location` は exact `scene.location_sequence[]` 内だけで選ぶ。終了側だけを `allowed_new_reveal_elements[]` と必要時の next-cut last-frame binding で許可する。場所をまたぐ binding は、遷移先が `scene.location_sequence[]` と current obligation の allowlist の双方に exact 宣言され、end/start state と reveal が exact match する場合だけ認める。

compiler は positive `constraints` に許可要素を列挙し、その要素以外の追加を禁止する。Kling の separate `negative_prompt` には正の allowlist 文と許可要素名を複写せず、「承認済み要素以外」の禁止だけを残す。positive allowlist と negative prohibition の両方に同じ要素名が入る request は矛盾として拒否する。

scene 全体の `visualizable_action` や `A→B→C` 形式の展開要約は review input であり motion source ではない。1 clip には cut の開始状態、単一主動作、終了状態だけを投影する。目標尺だけを理由に同じ動作の filler cut を追加しない。

## Materialization / Execution

frontend、CLI、scene storyboard の全経路で、provider call の前に `compile_video_api_prompt_v1` の結果を target の `video_generation.api_prompt_payload` へ保存する。

compiler v5 が返す full payload を field の削除・再解釈なしで保存する。次は Kling 固有 assertion の抜粋であり、payload の exhaustive field list ではない。

- `policy_version: video_api_prompt_v1`
- `compiler_version: conditional_video_prompt_compiler_v5`
- `projection_registry_version: video_prompt_projection_registry_v5`
- `provider_policy.multimodal_reference: false` / `provider_policy.negative_prompt_mode: separate`
- exact `prompt` / `negative_prompt`
- `source_digest` / payload `sha256`。review・request state の同じ値は `prompt_sha256` として束縛する
- `video_prompt_ir`（`video_prompt_ir_v2`）/ `projection_review_contract`（exact `review_only_sources[].value` と、caller dependency が正規化後に非空なら exact `review_only_dependencies` を含む）
- `video_prompt_ir.dependencies.has_references: false`
- `quality_issues[]`（Kling 実行可能 target は空配列）
- tool / duration / quality / aspect ratio / first / last（`references` は空であること）

render unit の `review_only_dependencies` は string trim と空 descendant 除去後に非空なら、exact normalized `render_unit_source_cut_ids` / `render_unit_source_cut_contracts` を `projection_review_contract.review_only_dependencies` に返して `source_digest` に束縛する。未指定または正規化後に空なら field は出さない。Kling の `prompt`、`negative_prompt`、top-level / IR の `included_fragments`、その他の `video_prompt_ir` fragment には出さない。

materialization 設定名は manifest template と同じ `review_prompt_fence`、`provider_prompt_sources`、`bind_materialized_reference_content_sha256`、`approval_request_flag`、`bind_negative_prompt`、`bind_provider_execution_options`、`reject_reserved_provider_extra_overrides` を使う。

`video_generation_requests.md` は同じ exact prompt と metadata を見せる review projection である。生成 API は materialized payload を provider request に使い、current design の再 compile 結果と prompt hash / source digest / settings を照合する。未 materialize、obsolete version、hash mismatch、design / setting / reference drift は再 materialize まで拒否する。

## Selection Loop

Kling は単発確定ではなく、同じ materialized request から複数候補を生成して選ぶ。

比較観点:

- 顔、衣装、小道具の continuity
- first frame からの自然な開始
- 主動作が一つに読めるか
- camera が主動作を邪魔していないか
- end state / last frame への到達
- 光、時間帯、空間方向の continuity
- 別 shot 化、fade、視点 jump の有無

候補が揃わない場合は prompt の禁止文を無限に継ぎ足さず、canonical motion、start frame、last boundary、shot 分割を見直して再 materialize する。

## Text-to-Video / Image-to-Video

### Text-to-Video

向いている用途:

- 導入の establishing shot
- 単発の情景 cut
- reference がまだない探索

同一人物の再現が必要な本番 cut で参照なし T2V を多用しない。

### Image-to-Video

向いている用途:

- character / object / location continuity が必要
- first frame で構図と見た目を承認済み
- first / last boundary を固定したい

motion はその静止画から起こせる変化に限定し、参照元にない要素を増やさない。

## 悪い例

```text
cut_function: payoff
target_beat: hero_event_07
主人公が走って振り向いて泣き、敵が現れて爆発する。その後カメラが急上昇し、フェードして街全体へ切り替わる。
```

問題:

- internal label / ID が provider text に漏れている
- 主動作が複数ある
- camera と編集点が多い
- 一つの連続 shot ではない
- event / reveal 境界を越える

改善時は provider 文だけを書き換えず、canonical cut を複数 intent に分ける。

## Agent 向け運用

- Director / Scriptwriter は story 設計で 1 clip 1 intent を壊さない
- p800 authoring agent は `cut_contract` を正本とし、Kling policy を満たす motion fields を設計する
- compiler / request materializer だけが `api_prompt_payload.prompt` を確定する
- semantic reviewer は `projection_review_contract` と `video_prompt_ir` を使い、event / reveal 境界と provider prompt の両方を確認する
- provider executor は editable draft を再解釈せず、materialized payload の一致 gate を通す

## 採用元メモ

[tanaka 記事](https://note.com/noz_tanaka/n/n553795d4619a) から、start frame と最初の shot の同期、cut 単位の分割、selection loop、shot card、短い shot を基本単位にする考え方を採用している。本 repo ではこれらを上記 canonical projection / materialization 契約へ統合する。
