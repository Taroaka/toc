# Asset Bibles（object / setpiece）: 正本

Asset bible は character、object、location、setpiece、phenomenon の reusable visual identity
を定義する。asset は単なる便利画像ではなく、複数 scene/cut の continuity anchor である。
生成は asset authoring → structural validation → request-bound generation の順で行う。

## 1. Asset stage → manifest

p500 の active slots:

- p510: source context と stage inputs の解決
- p520: `asset_inventory.md` で character/object/location/setpiece/reusable still を列挙
- p530: `asset_plan.md` で identity、purpose、reference、variant、output path を定義
- p550: immutable asset request を materialize
- p560: reusable asset を生成
- p570: continuity、file、decode、provenance を普通に検証

`script.md`、`story.md`、`visual_value.md`、`video_manifest.md` の source IDs と selector を
辿る。単発 shot の camera、pose、演技、background は scene/cut stage に残す。

## 2. Asset inventory and plan

```yaml
asset_plan:
  schema_version: asset_plan_v1
  source_artifacts:
    - path: story.md
      sha256: sha256:<hash>
    - path: script.md
      sha256: sha256:<hash>
  assets:
    - asset_id: character_01
      asset_type: character|object|location|setpiece|phenomenon|reusable_still
      story_purpose: ""
      source_script_selectors: []
      fixed_prompts: []
      reference_inputs: []
      derived_from_asset_id: null
      variants: []
      output_path: assets/characters/character_01.png
      creation_status: planned|created|stale|missing
      existing_outputs: []
```

Asset identity fields:

- character: same person identity、silhouette、costume/state、full-body front/side/back references
- object/setpiece: silhouette、material、scale、craft traces、mechanism、story purpose
- location: spatial identity、major structures、light/material、route
- variant: explicit `derived_from_asset_id` と state/time contract
- all assets: source selectors、reference paths、provider settings、output destination

`neutral_anchor` に scene 固有の time-of-day を焼き込まない。時間帯差分や state difference が
reusable である場合だけ explicit variant として定義する。variant は main reference から派生し、
別 identity を暗黙に作らない。

## 3. Asset request

```yaml
asset_generation_request:
  schema_version: asset_generation_request_v1
  generation_job_id: JOB_001
  item_id: character_01
  asset_id: character_01
  provider: codex_builtin_image
  execution_lane: bootstrap_builtin|standard
  prompt: "具体的に見える対象の日本語 prompt"
  negative_prompt: "短い禁止条件"
  prompt_sha256: sha256:<hash>
  source_digest: sha256:<hash>
  reference_inputs: []
  reference_content_sha256: {}
  destination: assets/characters/character_01.png
```

Provider prompt は drawable subject、material、light、composition、continuity constraints に
限定し、scene IDs、request metadata、debug keys、source paths、future motion を含めない。
`reference_inputs: []` は no-reference built-in lane、参照あり/derived asset は standard lane
として扱える。provider は current default `codex_builtin_image`。

## 4. Generation and ordinary checks

request を provider 呼び出し前に保存する。完了後に response item ID、prompt hash、source digest、
reference bytes、destination、file type、decode、content hash を照合する。binding が一致しない
output は quarantine し、同じ run の別 item に割り当てない。

p570/p600 で確認すること:

- character の顔、髪、年齢感、衣装、体格、full-body views
- object の silhouette、material、decoration、scale
- location の spatial identity、major structure、lighting
- variant の source identity と state transition
- `existing_outputs[]` と request-bound provenance
- PNG/JPEG/WebP の file type、画素が読めること、低情報量/placeholder でないこと

ローカル疑似ラスター、別 request の画像、存在しない reference、decode 不能 output は
canonical asset に採用しない。

## 5. Cinematic fields

```yaml
cinematic:
  role: "境界/誘惑/証拠/代償/帰還など"
  scene_usage:
    first_appearance: ""
    reveal_stage: concealed|hinted|featured|transformed|aftermath
    pressure_function: ""
    payoff_function: ""
  visual_takeaways: []
  spectacle_details: []
  continuity_risks: []
```

形、光、構造、機構、ショー性で観客に情報を渡し、看板、刻印、字幕、説明 UI に頼らない。
staged reveal は script の reveal constraints に従う。asset prompt で後段の情報を早出ししない。

[観客の理解と意味の設計](../story-creation.md#観客の理解と意味の設計) で反復要素を使う場合、
`story_purpose` と source selectors で登場場面へ結び、見た目の同一性は `fixed_prompts` で保つ。
`cinematic.scene_usage` は上流で決まった登場・役割を参照し、登場ごとの行動、構図、音や
意味の受け取られ方は scene/cut に残す。解釈が変わるだけなら別 asset / variant を作らない。
実際の外見・状態の変化が上流にある場合だけ、既存の variant 契約で表す。
反復自体は任意であり、音・行為・関係の反復のために画像 asset を発明しない。

## 6. Object and location examples

主役級 object/setpiece の最小 shape:

```yaml
object_bible:
  - object_id: artifact_01
    kind: artifact|setpiece|phenomenon
    reference_images: []
    fixed_prompts: []
    cinematic:
      role: ""
      visual_takeaways: []
      spectacle_details: []
    notes: ""
```

location の最小 shape:

```yaml
location_bible:
  - location_id: location_01
    reference_images: []
    reference_variants: []
    fixed_prompts: []
    continuity_notes: []
    notes: ""
```

同じ場所/物体を複数 cut で使う場合は stable ID と reference path を manifest へ投影する。
background glimpse は別 asset identity にせず、cut の `reference_usage` で関係を指定する。

## 7. Resume

upstream source digest、asset plan、request、reference bytes が変わったら downstream image
requests と stale outputs を再 materialize する。valid asset は bytes/provenance が current の
限り保持する。resume は state history を書き換えず、stale item だけを再生成する。

## References

- `docs/data-contracts.md`
- `docs/implementation/image-prompting.md`
- `workflow/asset-plan-template.yaml`
- `workflow/asset-inventory-template.yaml`
