# Requirements

## Summary

人レビュー用の `image_generation_requests.md` は、新規生成する scene/cut だけではなく、画像 prompt を持つすべての scene/cut を載せる。

## Requirements

1. 各 scene/cut は `still_image_plan.generation_status` を持てる。
   - `missing`
   - `created`
   - `recreate`
2. `missing` と `recreate` は再生成対象として扱える。
3. `created` は既定では再生成対象にしない。
4. `recreate` を `--force` で実行する場合、既存 canonical 画像は `assets/test/` へ退避してから上書きする。
5. `--force --test-image-variants N` は今後も使え、canonical 更新とは別に exploratory variant を複数出せる。
6. `image_generation_requests.md` には review 用に、画像 prompt を持つ全 scene/cut を出す。
7. request には少なくとも次を含める。
   - `still_mode`
   - `generation_status`
   - `plan_source`

