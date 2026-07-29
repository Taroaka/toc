# Design: `/toc-world-walk` + `world_walk`

## Approach

`/toc-world-walk` は完全な別 pipeline にせず、既存の immersive scaffold / stage / review contract に乗せる。

- 実体の分岐キーは `experience=world_walk`
- slash command は `.claude/commands/toc/toc-world-walk.md`
- 便利 wrapper は `scripts/toc-world-walk.py`
- manifest template は `workflow/immersive-world-walk-video-manifest-template.md`

## World Walk Visual Contract

- 視点は「観察者 POV」。カメラは世界の中を歩くが、主人公や参照キャラ本人の視点ではない
- カメラは中景〜遠景を基本にし、少し離れて物語を見かける
- 派手な演出、急接近、劇的カメラワーク、戦闘・爆発の強調を避ける
- 序盤に、物語が進まない asset 内散歩パートを置く
- 中盤以降、参照キャラが遠景に現れ、物語が別導線で始まっているのを観察する
- 観察者は物語へ介入しない

## Source Run Handling

`world_walk` は既存 asset を前提にするため `--source-run` を必須にする。
scaffold は asset をコピーせず、`video_manifest.md` に source path を記録する。
下流の作業者は source run の `assets/` から必要参照を選び、必要に応じて新 run の manifest references へ具体パスを入れる。

## Compatibility

既存の `cinematic_story`, `cloud_island_walk`, `ride_action_boat` はそのまま維持する。
`scripts/toc-world-walk.py` は wrapper に留め、stage target / review policy / video tool は `toc-immersive-ride.py` に委譲する。

