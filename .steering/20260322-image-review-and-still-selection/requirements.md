# Requirements

## Summary
- prompt に人物が出ているのに `image_generation.character_ids` が空の cut は review で fail にする
- story still の既定生成対象は `still_image_plan.mode: generate_still` のみにする
- `reuse_anchor` / `no_dedicated_still` は既定では生成しない

## Why
- 自然言語 prompt だけでは人物 reference が注入されず、scene03/05/06 のように人物欠落画像が出る
- prompt collection の review 対象と実際の image generation 対象がズレていて、review を通っていない cut が生成される

## Required behavior
- review script は prompt 内の人物 alias を検出し、`character_ids` が空なら fail reason を出す
- image generation runtime は story cut について `generate_still` だけを既定対象にする
- reference image (`assets/characters/*`, `assets/objects/*`) は従来どおり既定対象に含める
- 必要なら operator が CLI で `reuse_anchor` などを明示的に追加できる
