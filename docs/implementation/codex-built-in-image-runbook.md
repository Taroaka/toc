# Codex Built-in Image Runbook

Codex built-in image generation（想定モデル `gpt-image-2`）を ToC の image stage で使う。
参照あり/なしを問わず provider は `codex_builtin_image`。prompt、request snapshot、reference
bytes、output destination を保存し、完全な provenance が一致した画像だけを run に取り込む。

## 1. Run flow

1. stage author が current cut contract と asset references から prompt/request を作る。
2. request-bound snapshot と exact hashes を保存する。
3. 会話内の reference images を必要に応じて provider へ渡す。
4. built-in image generation を実行する。
5. response item、file type、decode、bytes、destination、provenance を検証して取り込む。

Hook は保存経路にせず、no-reference lane の guidance だけに使う。

## 2. Reference images

- path を prompt 本文へ書くだけではなく、実際の reference bytes を request に束縛する。
- continuity に必要な character/object/location のみを渡す。
- reusable character は顔、髪、衣装、姿勢、全身 front/side/back など stable identity を asset plan に書く。
- built-in の reference fidelity は provider capability の範囲であり、bytes/hash identity と同じ意味ではない。
- likeness が崩れた場合は、reference inputs、scene complexity、current asset variant を owning request で修正する。

Role labels は metadata に保存できる。

- identity continuity
- costume continuity
- prop continuity
- style anchor

## 3. Responsibility boundary

Skill/authoring contract が決めるもの:

- prompt source と projection
- reference paths と role labels
- batch item、命名、destination、import 手順
- no-reference と reference-driven lane

Runtime が検証するもの:

- request/provider item identity
- exact prompt/source/reference hashes
- expected saved path と destination
- output existence、image type、decode、bytes
- request revision と output provenance

## 4. Request-bound provenance

必須 fields:

```yaml
generation_job_id: JOB_001
item_id: scene_01_cut_01
kind: scene_image|asset
turn_id: turn_001
prompt_sha256: sha256:<prompt hash>
reference_sha256s: {}
savedPath: /runtime/generated/image.png
destination: assets/scenes/scene_01_cut_01.png
source: codex_builtin_image
```

workspace destination へ copy してよいのは、current request と上記 tuple が一致する画像だけ。
`generated_images` 時刻順 fallback は legacy/recovery signal とし、並列正規 route の source
にはしない。

使用 helper:

- [scripts/import-codex-generated-image.py](/Users/kantaro/Downloads/toc/scripts/import-codex-generated-image.py)

`--source` 省略時の latest image lookup は test/recovery 用。production では transcript/
response から item に束縛された savedPath を使う。既存 destination の overwrite は request
revision と明示した overwrite operation が一致する場合だけ許可する。

## 5. Asset lanes

- `reference_count == 0`: `execution_lane=bootstrap_builtin`（provider は built-in）
- `reference_count > 0` または `derived_from_asset_id`: `execution_lane=standard`

lane は routing metadata であり、quality status や approval state ではない。

## 6. Parallel batch

- 1 worker = 1 image item
- output destination は item ごとに固定する
- shared image parallelism default は 6（`TOC_IMAGE_GEN_PARALLELISM`）
- fallback lane を使う場合は `TOC_IMAGE_GEN_PROVENANCE_POLICY=serial_fallback` で実効並列数を 1 にする
- `generation_job_id / turn_id / savedPath / destination / prompt_sha256 / reference_sha256s` を
  provider 前後で照合する
- mismatch は該当 item だけを quarantine/retry し、他 item の結果を流用しない

## 7. Test procedure

Test output は run の `assets/test/` に保存する。

```bash
python scripts/import-codex-generated-image.py \
  --dest "output/<run>/assets/test/scene01_cut01__built_in_test.png"
```

test image を canonical asset に昇格する場合も、asset plan の destination、source digest、
reference bytes、file/decode checks を再検証してから copy する。

## 8. Hook

同梱 hook:

- `.codex/hooks.json`
- `.codex/config.toml`
- `.codex/hooks/post_tool_no_reference_image_lane.py`

hook は `NO_REFERENCE_IMAGE_LANE_REQUIRED` を検出して no-reference runner を案内できる。
保存 path 解決、workspace import、candidate選択、canonical promotion は hook が行わない。

