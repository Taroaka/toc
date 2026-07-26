# Cinderella long-form semantic regression requirements

## Goal

フロントから 600 秒のシンデレラを 1 回作成したとき、1 つの create job / run だけが開始され、story semantic QA が移動経路・出来事配分・隣接 scene handoff の不整合で失敗しないようにする。

## Success criteria

- `シンデレラ_20260722_2226` の後続 `2259` / `2310` が別の headless 検証 run であり、フロント操作の重複ではないことを provenance で確認する。
- 600 秒の duration expansion で、同一 canonical scene の sibling runtime scene が同じ multi-location route を再走しない。
- route continuity のためだけの non-action placeholder segment を生成しない。
- 600 秒でも探索、義姉たちの試着、排除、使者の介入、シンデレラの試着、公的確認を下流で描画可能な scene 責務へ配分する。
- focused regression test が修正前に失敗し、修正後に合格する。
- frontend と同じ backend create endpoint を使う `frontless_review` が、画像生成なし・600 秒で semantic QA を通過する。

## Scope

- duration-aware story expansion と Cinderella の long-form scene / route allocation
- story semantic repair が sibling route を再複製しないための最小契約
- focused unit / integration regression tests

## Out of scope

- 別 Codex が作成した `2259` / `2310` の修復や削除
- 生成済み画像の品質変更
- 既存 run artifact の手修正
- semantic QA retry 回数の単純増加

