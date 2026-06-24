# Codex Built-in Image Runbook

この文書は Codex built-in image generation（現行想定モデル: `gpt-image-2`）の運用メモであり、repo の標準画像パイプラインである。
repo では、参照あり/なしを問わず image request を `tool: codex_builtin_image` でこの経路へ回す。

目的: OpenAI API を使わずに、Codex built-in image generation を会話内で使い、採用画像を workspace に取り込む運用を固定する。

対象:

- 標準パイプラインの built-in image generation
- no-reference asset seed / scene still
- 参照画像を使う scene still
- test 用の `assets/test/` 保存
- 後で `thumbnail` 系にも転用したい batch 実行

## 結論

現時点の推奨運用は次の 3 段です。

1. skill が prompt と output contract を決める
2. 会話内で参照画像を見える状態にして built-in image generation を実行する
3. built-in の生成結果を script で workspace に move or copy する

hook は保存主経路にはしない。

理由:

- built-in image generation 自体は会話内運用と相性がよい
- 参照画像も会話に見える状態で渡せる
- 一方で lifecycle hooks は仕様がまだ弱く、生成画像の保存後処理を安定して自動化できる前提が薄い
- ただし no-reference lane へ切り替える指示を deterministic に返す用途には使える

## 参照画像の扱い

built-in image generation で local 画像を参照に使うときは、repo の file path を prompt に書くだけでは足りない。

原則:

- 参照画像は会話内で見える状態にする
- 各画像の役割を prompt に書く
- continuity に必要な画像だけを渡す
- ただし built-in image generation では、会話内で見えている参照画像だけで厳密な identity lock が保証されるとはみなさない
- したがってこの経路は `reference candidate generation` として扱い、完全再現が必要な工程とは分けて考える

役割ラベル例:

- `identity continuity`
- `costume continuity`
- `prop continuity`
- `style anchor`

検証ルール:

1. まず主役キャラクターを単体で生成し、顔・髪型・衣装の continuity を確認する
2. 次に必要なら相手役や小道具も単体で確認する
3. その後に scene cut へ進む

scene で likeness が崩れた場合は、「参照画像が見えていない」とは即断せず、「scene complexity に対して拘束が弱い」と判断する

## Skill Responsibility Boundary

この repo では、skill に期待することと、skill では解決しないことを分けて扱う。

skill で担保できること:

- どの prompt を使うか
- どの reference 画像を使うか
- reference の役割ラベルをどう書くか
- 単体 continuity test から scene cut へ進む順序
- batch 実行、保存先、命名、import 手順
- built-in image generation を `reference candidate generation` として扱う運用

skill だけでは担保できないこと:

- 人物 face identity の厳密固定
- 会話内参照画像だけに依存した exact character reconstruction
- multi-subject scene での強い identity lock
- built-in image generation の内部的な参照拘束強度そのものの制御

判断基準:

1. likeness の目標が「寄せる」なら skill + built-in で進める
2. likeness の目標が「同一人物として再現する」なら、skill だけでは不足と判断する
3. 特に人物 continuity が主目的なら、別ワークフローを検討する

別ワークフロー候補:

- face anchor と costume anchor を分けた reference 設計
- edit 中心の画像ワークフロー
- 人物 continuity 専用の review gate を p600 の前段に置く

## 保存の扱い

built-in image generation の初期保存先は workspace 直下とは限らない。

したがって project-bound な画像は、採用後に workspace へ取り込む。

保存の正本は request-bound provenance にする。
`generated_images` の時刻順 fallback は legacy / recovery mode の暫定救済であり、正規 route や並列実行時の正本にはしない。

必須 provenance:

- `generation_job_id`
- `item_id`
- `kind`
- `turn_id`
- `prompt_sha256`
- `reference_sha256s`
- `savedPath`
- `destination`
- `source`

workspace の destination へ copy してよいのは、この provenance が現在の request と一致した画像だけである。
`savedPath` が app-server transcript / response から request に紐付いて取れる場合はそれを primary path とし、`generated_images` 走査は debug / recovery signal に降格する。

使用 script:

- [scripts/import-codex-generated-image.py](/Users/kantaro/Downloads/toc/scripts/import-codex-generated-image.py)

既定動作:

- `--source` を省略すると `$CODEX_HOME/generated_images` 配下の最新画像を取る
- destination が既にある場合は `-v2`, `-v3` を自動採番する
- `--overwrite` を付けたときだけ上書きする

## Scene Test 手順

対象 run:

- `output/浦島太郎_20260208_1515_immersive`

test spec:

- [scene01-built-in-test-batch-spec.md](/Users/kantaro/Downloads/toc/output/浦島太郎_20260208_1515_immersive/assets/test/scene01-built-in-test-batch-spec.md)
- [scene01-built-in-image-prompts.md](/Users/kantaro/Downloads/toc/output/浦島太郎_20260208_1515_immersive/assets/test/scene01-built-in-image-prompts.md)

手順:

1. `urashima.png`, `urashima_refstrip.png`, `turtle.png`, `turtle_refstrip.png` を会話に見える状態にする
2. `scene1_cut1` の prompt で built-in image generation を実行する
3. 直後に次を実行して `assets/test/` に取り込む

```bash
python scripts/import-codex-generated-image.py \
  --dest "output/浦島太郎_20260208_1515_immersive/assets/test/scene01_cut01__built_in_test.png"
```

4. `scene1_cut2`, `scene1_cut3` も同様に繰り返す

## Subagent 運用

parallel 実行するときの原則:

- 1 subagent = 1 image item
- output path は item ごとに固定する
- 担当 L2 supervisor は spec と summary の bucket single writer になる
- 各 subagent は生成後に自分の output path にだけ import する
- Codex app-server 経由の production image generation は、request-bound provenance を正規 route として並列化する
- 並列化を有効にする場合、`generation_job_id / turn_id / savedPath / destination / prompt_sha256 / reference_sha256s` の一致を gate にする
- `generated_images_early_fallback` だけを根拠にした採用は、正規 route では fail または recovery-only 扱いにする

例:

- subagent A: `scene01_cut01__built_in_test.png`
- subagent B: `scene01_cut02__built_in_test.png`
- subagent C: `scene01_cut03__built_in_test.png`

production の bounded parallelism は request-bound provenance v2 を正規 route として使う。
`TOC_IMAGE_GEN_PARALLELISM` は既定 6 workers とし、必要に応じて env で調整する。
旧 `generated_images` fallback を使う場合だけ `TOC_IMAGE_GEN_PROVENANCE_POLICY=serial_fallback` を明示し、実効並列数を 1 に clamp する。

## Hook について

`hooks.json` ベースの lifecycle hooks は保存主経路にはしない。

ただしこの repo では、official Codex hooks の `PostToolUse` を使って、
`generate-assets-from-manifest.py` が返した `NO_REFERENCE_IMAGE_LANE_REQUIRED`
を拾い、`$toc-no-reference-image-runner` か `$toc-p500-bootstrap-image-runner`
へ切り替える deterministic guidance としては使ってよい。

同梱物:

- [hooks.json](/Users/kantaro/Downloads/toc/.codex/hooks.json)
- [config.toml](/Users/kantaro/Downloads/toc/.codex/config.toml)
- [post_tool_no_reference_image_lane.py](/Users/kantaro/Downloads/toc/.codex/hooks/post_tool_no_reference_image_lane.py)

役割の境界:

- hook がやること: no-reference を standard provider で再実行しないように指示する
- hook がやらないこと: built-in 生成物の保存 path 解決、workspace import、自動採用

この条件が崩れる限り、生成後 import は script のまま維持する。
