# Design: Scene semantic review shift-left

## Decision

scene reviewer の視点を作成工程へ前倒しする。ただし、同じ agent に自己採点させるのではなく、次の5層へ分ける。

1. **Criterion registry**
   - author と reviewer が参照する criterion ID、reason key、責務 owner、必要入力を一つに定義する。
2. **Scene-set authoring contract**
   - 全 scene の event ownership、reveal、role、time/location、handoff を scene 作成前に固定する。
3. **Authoring projection**
   - scene author / deterministic compiler は、自 scene の contract slice を入力にして scene draft を作る。
4. **Deterministic preflight**
   - scene 作成直後、cut 作成前に exact invariant を検証する。
5. **Independent semantic review**
   - frozen contract と canonical artifact を contextless に読み、意味品質と残存矛盾を判定する。

```text
story / visual_value / adaptation contract
                  |
                  v
       scene-set contract planner
                  |
          validate + freeze
                  |
       +----------+----------+
       |          |          |
   scene 10    scene 20   scene ... authoring
       |          |          |
       +----------+----------+
                  |
      deterministic scene-set preflight
                  |
            freeze scene set
                  |
          cut/materialization compiler
                  |
      independent contextless reviewer
                  |
             image generation
```

## Why this is not “run the same reviewer earlier”

同じ provider reviewer を scene ごとに追加すると、15 scene に author + critic の turn が増え、最終 review も残るため latency が悪化しうる。本設計では、次を provider call なしで前倒しする。

- exact ownership
- exact ID coverage / order
- monotonic reveal state
- role / participant closure
- handoff equality
- transition cue presence
- source / non-replaceable reference coverage

意味判断は authoring prompt に基準を渡し、必要な scene だけ targeted local repair を行う。全 scene に追加 critic turn を常設しない。

## Canonical components

### 1. `toc/scene_acceptance_contract.py`

既存 artifact 方式に合わせた plain Python module とする。

責務:

- schema / marker / criterion constants
- criterion registry
- scene-set authoring contract の cross-field validation
- scene draft と contract slice の照合
- cross-scene preflight
- semantic review prompt へ渡す criterion projection
- stable digest の計算

Pydantic を canonical artifact model にしない。`server/image_gen_app.py` の API input では Pydantic を使っているが、story/script/manifest は Markdown 内 YAML、未知 key を許容する dict、opt-in marker、custom cross-field rule を前提としている。Pydantic は必要なら API export model に限定する。

### 2. Criterion registry

criterion の文言を author prompt、validator、reviewer prompt に重複手書きしない。

```python
SCENE_ACCEPTANCE_CRITERIA = (
    {
        "criterion_id": "scene.canonical_event_ownership",
        "reason_key": "scene_event_canonical_event_missing",
        "owner": "deterministic",
        "first_enforced_stage": "scene_authoring_preflight",
        "semantic_recheck_stages": [],
        "provider_repair_allowed": False,
        "required_inputs": ["canonical_event_ledger", "scene_event.event_sequence"],
        "authoring_instruction": "割り当てられた source event を同順の owned beat として出力する",
        "reviewer_instruction": "原作上の出来事と意味が scene event で実質的に保たれるか確認する",
    },
)
```

`owner` は次のいずれかとする。

- `deterministic`: exact ID / state / reference / equality を preflight が hard gate する
- `authoring_semantic`: authoring prompt に必須条件として渡すが、意味判定は final reviewer が行う
- `independent_semantic`: author が自己 pass を宣言できず、final reviewer だけが合否を決める

同じ criterion が deterministic shell と semantic core を持つ場合は別 ID に分ける。例:

- `scene.causal_proof.references_complete` = deterministic
- `scene.causal_proof.visually_convincing` = semantic

registry は canonical JSON serialization の SHA-256 を持つ。criterion ID と canonical reason key は一意とし、canonical keyは `scene_set.semantic_subject_mismatch` のようにcriterion/stage namespaceを含める。改名・廃止は `legacy_reason_key_aliases[(stage, legacy_reason_key)] -> criterion_id` へ追加する。現行の `semantic_subject_mismatch` のように複数stageで共有される曖昧keyはlegacy reportでだけ読み、新reportはcriterion IDとcanonical reason keyを必ず出す。同じ version 文字列で内容 digest が変わった場合、review scope は fail-close する。semantic scope は `criterion_registry_version` と `criterion_registry_sha256` の両方へ束縛する。

`first_enforced_stage` は deterministic criterion を最初に hard gate する場所、`semantic_recheck_stages` は意味の再評価が必要な stage、`provider_repair_allowed` は provider repair へ送ってよい finding かを表す。`scene_detail` / `cut_blueprint` は preflight 済み deterministic criterion を provider で重複審査せず、contract / preflight digest の currentness だけを関数 verifier で確認する。

### 3. `scene_set_authoring_contract_v1`

新規 adaptation / cinematic story run は `script_metadata.scene_acceptance_contract: required_v1` を持つ。

作成時は先に JSON-compatible dict として build / validate / freeze し、最終的に `script.md.scene_set_authoring_contract` へ埋め込む。`video_manifest.md` は同じ巨大 block を第二の正本として複製せず、schema version、canonical script path、contract digest、scene slice digestだけを projection する。

authoring の唯一の向きは次とする。

```text
reviewed research / story / visual_value / adaptation contract
  -> scene_set_authoring_contract
  -> canonical_event_coverage_matrix compatibility projection
  -> scene_draft_v1
  -> cut / manifest projection
```

現行の `canonical_event_coverage_matrix` は scene event から後付け派生しているが、新契約では scene-set contract の compatibility projection に変更する。event ownership を別々に authoring しない。matrix と contract の不一致は deterministic failure とする。role、reveal、handoff も scene prose に別 source を持たず、contract の stable ID を scene draft が参照する。

```yaml
scene_set_authoring_contract:
  schema_version: scene_set_authoring_contract_v1
  generation_id: scene-authoring-<uuid>
  criterion_registry_version: scene_acceptance_criteria_v1
  criterion_registry_sha256: "..."
  source_bindings:
    research:
      path: research.md
      sha256: "..."
    story:
      path: story.md
      sha256: "..."
    visual_value:
      path: visual_value.md
      sha256: "..."
    adaptation_source_contract:
      artifact: story.md
      pointer: /adaptation_source_contract
      sha256: "..."

  source_refs:
    - source_ref_id: source_E01
      artifact: research.md
      artifact_sha256: "..."
      pointer: /events/E01
      expected_id: E01

  canonical_events:
    - event_id: E01
      canonical_order_index: 1
      owner_scene_id: 10
      required_beat_ids: [scene10_beat_01]
      source_ref_ids: [source_E01]

  evidence_catalog:
    - evidence_id: evidence_hearth_ash
      owner_scene_id: 10
      element_id: element_hearth_ash
      source_ref_ids: [source_E01]
      visible_form: "灰まみれの炉床と、その前で止められた手"

  reveal_ledger:
    - information_id: artifact_glass_slipper
      initial_state: withheld
      allowed_states: [withheld, revealed, carried, known]
      transitions:
        - reveal_transition_id: reveal_glass_slipper_scene50
          from_state: withheld
          to_state: revealed
          owner_scene_id: 50
          owner_beat_id: scene50_beat_02
          evidence_ids: [evidence_glass_slipper]

  handoff_chain:
    - anchor_id: handoff_10_20
      owner_scene_id: 10
      consumer_scene_id: 20
      state_id: state_after_scene10
      producer_beat_id: scene10_beat_01
      consumer_beat_id: scene20_beat_01
      evidence_ids: [evidence_hearth_ash]

  transition_cues:
    - transition_cue_id: cue_10_20_elapsed_time
      owner_scene_id: 20
      from_time_of_day: morning
      to_time_of_day: night
      owner_beat_id: scene20_beat_01
      evidence_ids: [evidence_night_window]

  scenes:
    - scene_id: 10
      owned_event_ids: [E01]
      required_beat_specs:
        - beat_id: scene10_beat_01
          source_event_ids: [E01]
          beat_function: setup
          required_role_ids: [protagonist]
          required_character_ids: [character_cinderella]
          required_evidence_ids: [evidence_hearth_ash]
          required_non_replaceable_element_ids: [element_hearth_ash]

      role_bindings:
        - role_id: protagonist
          character_ids: [character_cinderella]
          required_for_beat_ids: [scene10_beat_01]

      reveal_state_before:
        artifact_glass_slipper: withheld
      allowed_reveal_transition_ids: []
      reveal_state_after:
        artifact_glass_slipper: withheld

      time_location_transition:
        time_of_day: morning
        continuity_from_previous: opening
        transition_cue_required: false
        transition_cue_ids: []
        location_sequence: [location_kitchen]

      incoming_handoff_anchor_id: story_opening
      outgoing_handoff_anchor_id: handoff_10_20

      causal_proof_contract:
        cause_beat_id: scene10_beat_01
        action_beat_id: scene10_beat_01
        result_state_id: state_after_scene10
        required_evidence_ids: [evidence_hearth_ash]

      non_replaceable_elements:
        - element_id: element_hearth_ash
          source_ref_ids: [source_E01]
          required_evidence_ids: [evidence_hearth_ash]
```

`source_ref_v1` は `<artifact digest, parsed JSON Pointer, expected ID>` の組で、pointer の存在と expected ID を freeze 時に検証する。topic名から source を再生成したり、自由文だけを source ref として受理しない。

reveal state は schema が許可する enum と transition graph を持つ。`event_id / beat_id / evidence_id / role_id / character_id / handoff_anchor_id / transition_cue_id / reveal_transition_id` は非空・一意で、scene draft は prose の一致ではなく同じ ID を参照する。自由文は semantic reviewer の補助であり、deterministic pass の根拠にしない。

`authoring_preflight` は validator の結果だけを保存する derived block とし、scene の意味内容を再記述しない。

```yaml
authoring_preflight:
  status: pending
  generation_id: ""
  contract_digest: ""
  criterion_registry_digest: ""
  source_digest: ""
  preflight_digest: ""
  checks: []
  blocking_reason_keys: []
```

### 4. `scene_draft_v1`

deterministic compiler と AI author の共通出力契約とする。marker 付き run では top-level key を `schema_version / generation_id / scene_id / contract_digest / scene_slice_digest / scene_intent / scene_event / participants / handoff_refs` に限定し、未知 key、duplicate key、fence 外 text、digest mismatch を output-contract failure とする。

`scene_event.event_sequence[]` は contract の `required_beat_specs[]` を exact ordered mirror し、各 beat は次を ID で参照する。

- `source_event_ids[]`
- `role_ids[]`
- `participant_character_ids[]`
- `evidence_ids[]`
- `reveal_transition_ids[]`
- `transition_cue_ids[]`
- `incoming_handoff_anchor_ids[]` / `outgoing_handoff_anchor_ids[]`
- `result_state_id`

agent は contract field、ownership、ID、source digestを変更できない。parse / contract mismatch は semantic failure ではなく output-contract failure とする。default deterministic pathは追加 provider callを行わない。AI targeted repairを使う場合は1 sceneにつき最大1回、scene-set全体で最大3回とし、超過時は human / blockedへ送る。

`participants` と `handoff_refs` は次のshapeを持つ。

```yaml
participants:
  - character_id: character_helper
    role_ids: [helper]
    visibility: visible
    required_for_beat_ids: [scene60_beat_01]
    evidence_ids: [evidence_helper_gesture]

handoff_refs:
  incoming:
    - anchor_id: handoff_50_60
      state_id: state_after_scene50
      evidence_ids: [evidence_previous_anchor]
  outgoing:
    - anchor_id: handoff_60_70
      state_id: state_after_scene60
      evidence_ids: [evidence_current_anchor]
```

`visibility` は `visible | audible | offscreen_context` とし、required role closureは既定で`visible`を要求する。`offscreen_context`はrole coverageを満たさない。例外はcriterion registryがrole単位で`audible`を許可し、同beatのevidence IDがある場合だけ認める。

## Digest and generation contract

全digestは`sha256:<lowercase hex>`形式とする。contract / scene slice / preflight / registry は domain-separated canonical JSONをhashする。`source_bindings.*.sha256` と `source_refs[].artifact_sha256` だけは、JSONを含め保存artifactのraw bytesをhashし、空白・改行・duplicate-key表現を含むbyte差分もstaleとして拒否する。

```text
<domain tag> + NUL + UTF-8 canonical JSON
```

canonical JSONはmap keyを昇順、separatorを`,` / `:`、UnicodeをUTF-8のまま出力し、list順序を意味のある順序として保存する。domain tagは`toc.scene_acceptance.contract.v1`、`toc.scene_acceptance.scene_slice.v1`、`toc.scene_acceptance.preflight.v1`、`toc.scene_acceptance.registry.v1`のように対象ごとに分ける。

- contract digestからderived `authoring_preflight`とpublish metadataを除外する
- scene slice digestはcontract digestとscene IDを含む
- scene draft digestはslice digestとdraft本体を含む
- preflight digestはgeneration ID、contract、registry、source、ordered scene draft digests、check resultを含む
- targeted repairでdraftが変わった場合は同generationを上書きせず、新generation IDと`parent_generation_id`を作る
- repair後はaffected scene-local checksだけでなくwhole-set preflightを再実行し、旧semantic scope / reportをinvalidateする
- contractまたはsourceが変わるrepairも新generationとして最初からfreezeする

## Authoring flow

### Phase A: Plan the whole scene set

入力:

- review済み `research.md`
- reviewed `story.md`
- `visual_value.md`
- `adaptation_source_contract`
- character / object / location identity

出力:

- ordered scene list
- event ownership ledger
- reveal ledger
- role bindings
- time/location transition ledger
- handoff chain
- source-specific evidence obligations

この phase では cut、camera、lens、image prompt、motion prompt を作らない。

### Phase B: Validate and freeze the plan

個別 scene を作る前に次を hard gate する。

- required canonical events が exactly once ownership を持つ
- canonical order と scene order が矛盾しない
- reveal state が `withheld -> revealed -> carried/known` の方向にだけ進む
- handoff anchor が terminal を除き one producer / one consumer を持つ
- role binding が未知 character を参照しない
- time/location discontinuity に cue requirement が定義される
- non-replaceable elements が source refs を持つ

contract 自体が fail した場合、scene prose の repair へ進めず planner を修正する。

### Phase C: Author scenes from frozen slices

現在の `_build_script_and_manifest()` 単一ループを、少なくとも次の二段階に分ける。

1. 全 scene の intent / event draft を作る
2. scene-set preflight pass 後に cut coverage / cut contract / manifest を作る

scene author / deterministic compiler の入力は次に限定する。

- global source binding
- current scene contract slice
- previous outgoing handoff
- next incoming handoff
- criterion registry の authoring instructions

`include_artifact`、keyword inference、scene index のような局所 heuristic を、reveal / role / event ownership の source of truth にしない。これらは contract build 時の candidate helper としてだけ使い、freeze 後は ledger を読む。

既存コードへの主要な gate は次の3点とする。

1. `_scene_event_for_cut_design()` 直後、`_scene_cut_coverage_plan()` 前: scene-local preflight
2. 全 scene draft が揃った後、cut materialization 前: cross-scene preflight
3. `_build_script_and_manifest()` 後、script / manifest write と semantic pack 作成前: external fail-closed gate

3 は 1 / 2 の代用ではなく、別 caller が不正 artifact を materialize しないための defense in depth である。

全生成物は canonical path へ逐次書き出さず、generation 単位の staging に置く。

```text
logs/authoring/staging/<generation_id>/
  contract.json
  criterion_registry.json
  scene_drafts/<scene_id>.json
  preflight.json
  script.candidate.md
  video_manifest.candidate.md
  publish.journal.json
```

aggregate preflight、cut validation、source / registry currentness がすべて pass するまで canonical `script.md`、`video_manifest.md`、request artifact へ publish しない。publish は run-exclusive lock の下で行い、`publish.journal.json` に `planned -> staged -> validated -> publishing -> published` を残す。途中失敗時は canonical artifact を旧世代のまま維持し、staging generation を failed として隔離する。

### Phase D: Deterministic preflight

preflight は cut materialization 前に行う。

主な check:

| Check | 判定 |
|---|---|
| canonical event coverage | ledger の event / beat ID と scene event が exact ordered match |
| reveal monotonicity | state before / allowed reveal / state after と scene prose contract が一致 |
| role closure | required roles -> bound character -> participants / visible actors が閉じる |
| handoff ownership | current outgoing と next incoming の anchor ID / owner / consumer / state が一致 |
| route continuity | location sequence order と segment coverage が一致 |
| daypart continuity | discontinuity 時に non-empty cue がある |
| source specificity shell | required non-replaceable ID と source ref と visual evidence ref が存在 |
| causal proof shell | cause beat / visible action / visible result / evidence ref が同一 beat へ結合 |

preflight report:

```text
logs/authoring/scene_acceptance/preflight.json
logs/authoring/scene_acceptance/scenes/<scene_id>.json
```

state:

```text
authoring.scene_set.contract.status=pending|validated|failed
authoring.scene_set.contract.path=...
authoring.scene_set.contract.digest=...
authoring.scene_set.generation_id=...
authoring.scene_set.preflight.status=pending|passed|failed
authoring.scene_set.preflight.digest=...
authoring.scene_set.preflight.source_digest=...
authoring.scene_set.preflight.criterion_registry_digest=...
authoring.scene_set.preflight.error_count=N
authoring.scene_set.preflight.failed_scene_ids=...
```

state は append-only helper で更新する。source、contract、registry、scene draft のいずれかの digest が変わった場合は、同 generation の preflight / semantic reviewをcurrentとみなさず、明示的な invalidation snapshotを追記する。

### Phase E: Targeted authoring repair

- deterministic failure: provider reviewer を呼ばず、該当 scene producer または planner へ戻す
- local semantic risk: current scene と adjacent handoff だけを targeted repair context にする
- source meaning / event ownership change: human approval
- all scene に常設 critic turn は追加しない
- targeted provider repair は1 scene最大1回、scene-set全体最大3回とする。budget超過時は無制限loopへ入らず blocked / human reviewへ送る

### Phase F: Independent final review

final `scene_set` reviewer は次だけを読む。

- canonical story / script / manifest projection
- frozen scene-set contract
- criterion registry version
- criterion registry digest
- deterministic preflight report / digest

authoring transcript、self-review、producer の pass 宣言は入力にしない。

final reviewer が deterministic-owned reason key を返した場合も block は維持するが、同時に次を記録する。

```text
review.semantic.scene_set.shift_left_escape.count=N
review.semantic.scene_set.shift_left_escape.reason_keys=...
review.semantic.scene_set.shift_left_escape.preflight_digest=...
```

これは reviewer を弱める例外ではなく、validator / registry / fixture を改善するための defect signal である。

deterministic-owned finding は通常の semantic producer repair へ送らず、`shift_left_escape` として authoring validator / contract planner の修正経路へ戻す。`scene_detail` / `cut_blueprint` は同じ deterministic criterion を provider blocker として再実行せず、それぞれの stage 固有 semantic criterionだけを評価する。

## Generic fallback policy

generic prose の禁止語判定だけでは意味品質を保証しない。次の構造で縮退を防ぐ。

- `required_non_replaceable_element_ids` が visual evidence / event beat に参照される
- evidence は source ref を持つ
- handoff は generic description ではなく stable anchor ID と source-specific state を持つ
- causal proof は cause / action / result / evidence を同じ beat に束縛する

既存の「人物の姿勢、手元、物の位置」「床や道具に残る痕跡」は fallback sentence として source of truth にしない。source-specific element が解決できない場合は authoring failure とする。

## Templates and agent memory

会話履歴を持たない agent のため、次を同じ変更で更新する。

- `docs/story-creation.md`: authoring order と semantic ownership
- `docs/data-contracts.md`: marker、artifact、state、review boundary
- `docs/implementation/agent-roles-and-prompts.md`: planner / author / reviewer の分離
- `workflow/script-template.yaml`: コメント付き `scene_set_authoring_contract` 形
- `workflow/scene-outline-template.yaml`: scene slice ref と computed-only `authoring_preflight` 形
- `workflow/video-manifest-template.md`: canonical ref / digest projection
- stage grounding readset: 上記 doc / template / registry module

Markdown comment は「どう埋めるか」を教える。plain validator は「埋めた結果が成立するか」を判定する。どちらか一方だけを正本にしない。

## Reviewer prompt integration

`server/image_gen_app.py` の scene-set reason key list と、`toc/review_loop.py` の rubric prose を registry projection から生成する。

semantic reviewer 固有の自然言語説明は残してよいが、criterion ID / reason key / owner / required input は registry と不一致にできない。

review pack / scope は registry versionだけでなくregistry digest、generation ID、contract digest、preflight digest、source digestを持つ。どれかがcurrent artifactと一致しない場合はprovider起動前にfail-closeする。旧reason keyはalias mapで読み取れるが、新reportはcanonical reason keyだけを出す。

`toc/semantic_pack_scene.py` は scene-set / scene-detail の canonical pack builder として、scene intent / event の複数 fallback path から role/reveal/handoff を再推論せず、frozen contract slice と canonical output を並べて reviewer へ渡す。`toc/semantic_pack_image.py` は cut / image 系の downstream projection が同じ contract digest と矛盾しないことを確認する側に限定する。

## Compatibility

### New runs

- marker `script_metadata.scene_acceptance_contract: required_v1` を必須にする
- contract / preflight が pass するまで cut materialization しない

### Legacy runs

- markerなし: new preflightをskipし、現行semantic pathを使う。stateに`authoring.scene_set.preflight.status=legacy_not_applicable`を残す
- markerあり + complete supported version: new contract pathを必須にする
- markerあり + partial contract: scene authoring開始前にfail-closeする
- markerあり + unsupported version: compatibility fallbackへ落とさず`unsupported_scene_acceptance_contract_version`でblockする
- legacy reportの旧reason keyはregistry alias mapで読めるが、legacy artifactへ新markerを自動付与しない

### Current Cinderella

現在の Cinderella は既に p400 `script.md` / `video_manifest.md` を持つ。p500 resume はこれらを preserve するため、新しい authoring contract を実装しても p500 から再開するだけでは適用されない。

同じ run へ適用する場合は、別の checkpointed p400 rebuild を使う。正本planは `p400_rebuild_plan_v1` とする。

```yaml
schema_version: p400_rebuild_plan_v1
run_binding:
  run_id: "..."
  run_root_device: 0
  run_root_inode: 0
checkpoint_id: "..."
generation_id: "..."
state_before_sha256: "..."
preserved_sources:
  - path: research.md
    sha256: "..."
  - path: story.md
    sha256: "..."
  - path: visual_value.md
    sha256: "..."
replaced_artifacts: []       # path + sha256
invalidated_downstream: []   # p500+ path + sha256
reuse_policy: no_p500_plus_reuse_v1
invalidated_state_prefixes:
  - runtime.resume.p500.
  - slot.p5
  - slot.p6
  - artifact.
  - orchestration.p5
  - orchestration.p6
bulk_job_precondition: no_queued_or_running_jobs
checkpoint_dir: logs/resume/p400/<checkpoint_id>
candidate:
  contract_sha256: "..."
  script_sha256: "..."
  video_manifest_sha256: "..."
  preflight_sha256: "..."
  registry_sha256: "..."
  implementation_revision: "git/tree or code fingerprint"
plan_token: "digest bound to every field above"
```

この migration は `resume-from-p500.py` に暗黙追加しない。dry-run / plan-token / apply を持つ専用 entrypoint とし、次の transaction contractを守る。

1. prepare/dry-run段階でactive artifactを変更せず、`logs/authoring/staging/<generation_id>`へ新p400 candidateをbuild / preflight / validateする
2. candidate contract、script、manifest、preflight、registry、implementation revisionのdigestをplanへ入れ、plan tokenをcandidate bytesまで束縛する
3. applyはcandidateを再生成せず、prepare済みstaging bytesがplanと完全一致する場合だけpublishする
4. apply開始時にfrontend create / resume と同じexclusive run lockを取得し、queued/running bulk image jobがないことを確認する
5. run directory identity、state-before digest、preserved source digest、全replace/invalidate artifact digest、candidate digestを再検証する
6. plan tokenはcheckpoint IDと全digestへ束縛し、checkpoint作成済みtokenの再利用を拒否する
7. commit journalを`planned -> checkpointed -> published -> state_invalidated -> completed`で進める
8. commit時に旧script/manifest/p400 reviewと全p500+ artifactをcheckpointへ移し、active pathから旧selector/request/mediaを除く
9. selectorまたはmanifest digestが変わるv1では旧p500+ asset/request/imageを再利用しない。bytesはcheckpointに保存するだけとする
10. append-only stateへp410以降のslot、`runtime.resume.p500.*`、artifact path、p500/p600 orchestrationをpending/invalidatedへ戻すsnapshotを追記する
11. `p000_index.md`と`run_status.json`はnew stateから再生成し、旧derived statusを使わない
12. publish前失敗はactive runを無変更で終える。checkpoint後/publish中失敗はjournalから旧artifactを復元し、append-only stateへrollback結果を追記する
13. crash後はjournalを読んでcompleteまたはrollbackできる。手動削除やstate履歴の書換えを要求しない

rebuildは現在runのreview済みsource bytesをhash固定して使い、topic名からresearch/storyを再生成しない。

## Implementation surfaces

- `toc/scene_acceptance_contract.py` — registry / validator / digest / prompt projection
- `scripts/toc-immersive-frontend-run.py` — whole-set planning、two-pass materialization、preflight gate
- `toc/semantic_pack_scene.py` — contract-bound scene-set / scene-detail projection
- `toc/semantic_pack_image.py` — downstream cut / image projection currentness
- `toc/review_loop.py` — registry-backed criterion projection
- `server/image_gen_app.py` — reviewer prompt reason keys、escape telemetry、repair routing
- `workflow/script-template.yaml`
- `workflow/scene-outline-template.yaml`
- `workflow/video-manifest-template.md`
- `workflow/stage-grounding.yaml`
- `docs/story-creation.md`
- `docs/data-contracts.md`
- `docs/implementation/agent-roles-and-prompts.md`
- new p400 rebuild entrypoint and checkpoint contract

## Verification strategy

### Contract unit tests

- duplicate / missing event ownership
- reveal rollback after first reveal
- role without character binding
- participant / visible actor closure failure
- duplicated / unowned handoff
- route order mismatch
- daypart jump without cue
- missing source ref / non-replaceable evidence
- causal proof reference mismatch
- scene draftがcontract IDを変更・欠落するoutput-contract failure
- source / registry / preflight generation digest mismatch

### Golden Cinderella regression

Known-bad fixture must fail with stable reason keys for:

- post-reveal withheld glass slipper
- helper / crowd omission
- current-scene action attributed to previous handoff
- morning-to-night change without elapsed-time cue
- canonical event present only in review-only text
- generic evidence replacing source-specific object/action

Corrected fixture must pass preflight before any semantic provider call.

### Pipeline integration

- preflight failure prevents cut / request materialization
- preflight failure generationがcanonical script / manifestへ一切publishされない
- preflight pass freezes digest into script, manifest, semantic scope
- final reviewer receives matching digest / registry version
- deterministic final finding records shift-left escape
- marker-less legacy run follows compatibility path
- markerありpartial / unsupported versionがfail-closeする
- scene_detail / cut_blueprintがpreflight-owned deterministic criterionをprovider repairへ重複送信しない
- p400 rebuildのplan token改ざん・再利用・途中失敗・旧p500残留を拒否する

### Latency evidence

Record:

- `authoring_preflight_seconds`
- `scene_set_semantic_attempts`
- `producer_repair_rounds`
- `shift_left_escape_count`
- time from p400 authoring start to scene-set pass

Acceptance limits:

- 20 scenesのcontract build + deterministic preflightは通常環境でp95 2秒以内
- pass pathの追加mandatory provider callは0
- targeted repairは1 scene最大1回、scene-set全体最大3回
- known-bad deterministic fixtureはsemantic provider call 0回
- corrected Cinderella goldenはscene-set semantic attempt 1回、producer repair 0回
- scene_detail / cut_blueprintはpreflight-owned deterministic criterionのためにprovider call / repair roundを追加しない
- authoring scene sliceは1 scene 64 KiB以下を目標にし、全contractを各scene promptへ複製しない

baselineとの差は`semantic_attempts / producer_repair_rounds / p400開始からscene-set passまでの時間`で報告する。

ここで`scene-set semantic attempt 1回`はcanonical aggregate generation 1回を意味する。15 sceneなら通常は15 shard provider turnsを含むため、`aggregate_attempts`と`shard_provider_turns`を別々に記録する。corrected 15-scene goldenの期待値はaggregate 1、semantic repair 0、transport retryがなければshard turns 15である。

## Rollout

1. add registry / validator / fixtures behind opt-in marker
2. update templates / grounding / authoring prompt
3. enable two-pass materialization for new frontend runs
4. bind semantic pack / reviewer prompt to contract digest
5. enable escape telemetry and targeted repair
6. add checkpointed p400 rebuild for the existing Cinderella run
7. make marker default after golden runs pass
