# Requirements

## Goal

script の `evaluation_contract.reveal_constraints` を image / manifest evaluator が読み、指定 cut より前での早出しを自動で検出できるようにする。

## Requirements

- `review-image-prompt-story-consistency.py` は script-level `reveal_constraints` を読み、`must_not_appear_before` に反する prompt / `character_ids` / `object_ids` を finding にする
- `review-manifest-stage.py` が使う manifest evaluator も同じ reveal contract を読み、manifest 全体として script の初出制約を破っていれば fail にする
- reveal 判定は `sceneYY_cutZZ` の順序で比較し、対象 cut 以前だけを違反として扱う
- image review の canonical reason key を追加し、docs / templates に契約の読み取り元を明記する
- 既存 run の prompt 本文は変更しない
- reveal 制約をカバーする回帰テストを追加する
