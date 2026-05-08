# Image Generation UI

## Purpose

`/image_gen` は `output/<run>/` にある image generation request を読み込み、prompt と reference image を確認しながら、candidate image を生成・比較・採用する画面である。

右側 chat pane は画像生成ログではなく、ユーザーと Codex app-server の通常チャットに限定する。

## Screen Structure

画面は左右 2 pane 構成にする。

- Left workspace: folder selection, asset / scene tab, asset sub-filter, candidate count, generation grid, bulk footer
- Right chat pane: user chat, assistant response, approval UI

PC 幅では left workspace の prompt grid は 2 columns。狭い viewport では chat pane を隠し、grid は 1 column にする。

## Vertical Order

Left workspace の順序:

1. output folder selector
2. `asset` / `scene` tabs
3. 同時生成枚数 area
4. image generation grid
5. fixed bulk footer

この順序は変えない。ユーザーは「どの run」「asset か scene か」「asset の場合は chara / obj / asset のどれか」「何枚作るか」を決めてから grid を操作する。

`chara` と `obj` は scene と同列の top-level tab ではなく、`asset` 側の sub-filter として置く。sub-filter の選択肢は `chara -> obj -> asset` の順に並べる。どれも独立した request file ではなく、`asset_generation_requests.md` 内の filtered view として扱う。`chara` は `asset_type` に `character` を含む item、または output が `assets/characters/` 配下の item を表示する。`obj` は `asset_type` に `object` を含む item、または output が `assets/objects/` 配下の item を表示する。`asset` は asset 全体の表示であり、その中の item order も `chara -> obj -> その他asset` の順にする。

## Grid Card

各 grid card は 1 request item を表す。

必須要素:

- item id
- output path
- execution lane
- prompt text field
- reference image multi-select
- single generate button
- existing image preview
- generated candidate area

reference dropdown の item は thumbnail と拡張子なし filename を並べる。

## Candidate Area

candidate area は画像比較のための領域であり、prompt card 内の最重要 visual area として扱う。

ルール:

- candidate image は 16:9
- selected candidate は primary accent の border で示す
- failed candidate は画像枠を崩さず、短い error text を表示する
- existing image は比較対象として表示してよいが、candidate とは視覚的に区別する

## Bulk Footer

bulk footer は `flex-shrink: 0` とし、grid scroll に巻き込まない。

必須 action:

- 一括生成
- 一括ダウンロード zip
- 一括 repo 内挿入

repo 内挿入は canonical output path を上書きする可能性があるため、単なる保存ではなく採用操作として扱う。

## Empty / Loading States

- run 未選択: grid を空にし、folder selector の選択を促す
- request file なし: tab は表示し、grid に短い empty state を出す
- loading: grid area に progress を出す
- generation in progress: 対象 card の button と candidate area で状態表示する

画像生成ログは right chat pane に流さない。
