# Video Prompt Projection / Compilation

動画の story / scene / cut design を、provider に渡す短い motion prompt へ安全に投影する。
全体の運用は `docs/video-generation.md`、Kling 固有の制約は
`workflow/playbooks/video-generation/kling.md` を参照する。

## 正本境界

```text
story / scene / cut canonical design
  → video prompt projection registry
  → compile_video_api_prompt_v1
  → video_generation.api_prompt_payload
  → immutable request snapshot
  → provider API
```

- canonical design は物語上の責務、event/reveal 境界、開始状態、主動作、終了状態、continuity を持つ。
- registry は各 key の authoring relevance と provider projection を分類する。
- compiler は active な情報だけを provider-facing fragment へ変換する。
- provider が読む正本は materialize 済み `api_prompt_payload.prompt` である。
- `prompt_authoring_source` と legacy `motion_prompt` は input/read alias であり、canonical design を上書きしない。
- `cut_function`、target/event/reveal ID、path、hash、image prompt、narration、production metadata は
  provider prose に出さない。

### Identity

- authoring identity: canonical story/scene/cut design と、canonical group が空のときだけ使う fallback source
- compiler identity: policy/compiler/registry version と normalized compilation source digest
- provider-request identity: materialized prompt/negative prompt/hash/provider binding/request revision

同じ prompt text でも frame、reference bytes、model、duration、source digest が変われば別 request である。

## 入力の優先順位

1. `cut.cut_contract.first_frame_contract`
2. `cut.cut_contract.motion_contract`
3. `cut.cut_contract.continuity_contract`
4. `cut.cut_contract.viewer_contract` と `source_event_contract`
5. flat legacy motion contract
6. `prompt_authoring_source` / legacy `motion_prompt`（canonical value がない場合のみ）

上位 source が値を持つ group へ、下位 source の競合値を継ぎ足さない。fallback は event boundary、
end state、identity を変更できない。

## Projection registry

code source of truth は `toc/video_prompt_projection_registry.py`、version は
`video_prompt_projection_registry_v5`。

| axis | values | purpose |
| --- | --- | --- |
| `authoring_relevance` | `required|conditional|none` | design input の要否 |
| `provider_projection` | `derive|may_surface|must_not_surface` | provider text への投影 |
| `trace_visibility` | `projection|excluded|none` | materialization diagnostics への記録 |

各 rule は `source_keys`、`target_group`、`transform`、`structural_checks`、provider に出さない
場合の `exclusion_reason` を持つ。

Canonical provider fragment order:

1. `start_state`
2. `primary_motion`
3. `camera_motion`
4. `environment_motion`
5. `emotional_change`
6. `end_state`
7. `continuity`
8. `constraints`

空の optional group は出力しない。design IDs、scene-wide summary、image/narration prose、
internal references は diagnostics に留め、prompt 本文へ入れない。

主な投影:

- `motion_contract.motion_brief` → `primary_motion`
- `motion_contract.camera_motion` → `camera_motion`（存在時）
- `motion_contract.end_state` → `end_state`
- `video_metadata.time` / `scene.time_of_day` → `continuity`
- `allowed_new_reveal_elements[]` → `constraints`（exact obligation の allowlist）
- `image_generation.references[]` は image input のまま保持し、video references へ暗黙継承しない

## Compiler contract

```yaml
api_prompt_payload:
  policy_version: video_api_prompt_v1
  compiler_version: conditional_video_prompt_compiler_v5
  projection_registry_version: video_prompt_projection_registry_v5
  provider: kling_3_0
  mode: image_to_video
  provider_policy:
    one_clip_one_intent: true
    max_camera_instructions: 2
    single_continuous_shot: true
    first_last_frame_boundary: false
    negative_prompt_mode: separate
  provider_request_binding:
    duration_seconds: 8
    quality: 1080p
    aspect_ratio: "16:9"
    first_frame: assets/scenes/scene01_cut01.png
    last_frame: ""
    references: []
    reference_roles: []
    reference_content_sha256: {}
    execution_options: {}
  prompt: "<exact provider-facing motion prompt>"
  negative_prompt: "<compiled constraints>"
  source_digest: "<normalized source hash>"
  sha256: "<exact prompt hash>"
  included_fragments: []
  omitted_groups: []
  structural_issues: []
  projection_trace:
    excluded_sources: []
    shadowed_sources: []
    authoring_source_normalization: {}
  video_prompt_ir:
    schema_version: video_prompt_ir_v2
    dependencies: {}
    included_fragments: []
    omitted_groups: []
```

`prompt` is exact provider text; `sha256` hashes its UTF-8 bytes. `source_digest` covers canonical
design, policy/compiler/provider/mode, duration/settings, first/last/reference content hashes, execution
options, fallback input, and projection result. A changed design cannot reuse an old payload.

## Boundary and reveal rules

First frame is the departure boundary, last frame is the arrival boundary. A single continuous shot reaches
the end state. Do not insert a fade, cut, dissolve, viewpoint jump, completed action, future reveal, unlisted
character/object, or unlisted location.

An exact obligation may declare:

- `allowed_new_reveal_elements[]`: concrete elements that may appear through the main motion
- `allowed_reveal_info_ids[]`: source reveal IDs unlocked by that cut
- `use_next_cut_first_frame_as_last_frame`: bind arrival bytes to the next cut's first frame

These keys live only under that obligation. Validate non-empty unique allowlist, source grounding, no
intersection with `must_not_add`, and exact match between current end state and next first frame.

## Provider modes and reference binding

- no first frame: `text_to_video`
- first frame: `image_to_video`
- first and last frame: `first_last_frame`
- ordered auxiliary references without frame boundary: `reference_to_video`

```yaml
video_input_contract:
  schema_version: render_unit_video_input_v1
  input_mode: reference_images
  required_references:
    - assets/scenes/scene01_cut01.png
    - assets/scenes/scene01_storyboard.png
  reference_roles:
    - image_index: 1
      role: start_state_visual_anchor
    - image_index: 2
      role: ordered_storyboard_sequence_guide
```

Reference roles are the same length, order, and indices as required references. The materializer copies
them into provider binding, IR dependencies, and source digest. Paths, asset IDs, and hashes stay in
metadata. Frame-boundary and auxiliary-reference modes are mutually exclusive when the adapter cannot
send both.

Kling uses one clip/one intent, at most two camera instructions, and a single continuous shot. Seedance
reference-image mode uses its selected model capability for duration and reference count. Never assume a
shared provider limit.

## Render units

`scenes[].render_units[]` can group ordered cuts into one provider clip.

- `unit_id` is unique; `source_cut_ids[]` is non-empty, canonical order, exactly once.
- unit duration equals source cut duration sum and stays within provider capability.
- the unit contract inherits first-frame start, final end state, continuity, and all source prohibitions.
- one unit has one primary motion; individual cut actions are not concatenated into an unbounded prompt.
- explicit reveal allowlist equals the stable deduped source union exactly; missing or extra elements fail.
- source cut IDs/contracts are stored in `projection_trace` and `source_digest`, not provider prose.

## Materialization and execution

Frontend, server, CLI, and storyboard use the same compiler. Before a provider call, save the payload and
request snapshot containing:

- exact prompt/negative prompt and hashes
- policy/compiler/registry versions
- source digest and request revision
- provider/model/mode/settings
- first/last frames, ordered references/roles, reference content hashes
- destination and execution options

Before execution, recompile current design and compare every field. Missing payload, malformed data, unknown
reference, settings drift, hash mismatch, source digest mismatch, or destination drift is a stale request
error. Repair the owning design/request and materialize again.

After execution, verify provider item identity, turn/job ID, prompt hash, reference hashes, saved path,
destination, file existence, type, decode, frames/stream, duration, and content hash. A mismatched output is
quarantined and never assigned to another request.

## Ordinary structural checks

- unique scene/cut/event IDs and valid source/selector/handoff references
- one primary intent and exact event/obligation coverage
- first-frame imageability and motion start/end boundary
- location/time continuity and reveal allowlists
- prompt fragment order and empty-group omission
- request snapshot/payload/source digest/provider binding equality
- provider capability, frame/reference count, file/decode, duration, and stream compatibility

A failed check names its owning artifact and selector. The owner repairs the source contract and reruns the
compiler. Do not patch compiled prompt text to hide a source error.

## References

- `docs/video-generation.md`
- `docs/implementation/video-integration.md`
- `docs/data-contracts.md`
- `workflow/playbooks/video-generation/kling.md`

