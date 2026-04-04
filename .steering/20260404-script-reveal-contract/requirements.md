# Requirements

## Goal

`script.md` に、物語全体の reveal order / first appearance を evaluator が参照できる形で明示する。

## Why

- scene / cut 実装が script の reveal 設計を破っても、現状は narrative reviewer が明示的に拾えない
- 「乙姫の初出は scene04_cut05 以降」のような制約を上位契約として持つ必要がある

## Requirements

1. `script.md` に global reveal contract を置ける
2. contract は character / object / event の初出や早出し禁止を表現できる
3. current run の `output/浦島太郎_20260208_1515_immersive/script.md` にも反映する
4. docs / templates も同じ schema を示す

