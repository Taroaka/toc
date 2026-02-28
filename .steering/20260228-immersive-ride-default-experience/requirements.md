# /toc-immersive-ride: Default experience switch (requirements)

## Background / Problem

本リポジトリの「没入型」系ドキュメント/テンプレでは、`ride_action_boat`（ボート + 安全バー + 手元アンカー + First-person POV）を前提にした記述が目立ち、今後の新規生成でそれら（ボート/手/年齢など）が **必須条件**であるかのように誤解されやすい。

既存の `output/`（過去生成物）は現状のままで良いが、今後の新規生成の指示書（doc / agent prompt / scaffold の default）には、これらの固定条件を **デフォルトとしては含めない**ようにしたい。

## Goals

- `/toc-immersive-ride` のデフォルト experience を `cloud_island_walk` に変更し、何も指定しない新規生成で `ride_action_boat` の固定条件が入らないようにする
- ドキュメント/エージェント指示の「default」表記を最新に揃える
- 年齢（例: 20代）の固定指定は撤去し、必要時のみ作品側で指定できる形にする
- `ride_action_boat` は **明示指定した場合のみ**利用できる（後方互換として残す）

## Non-goals

- 既存の `output/` 配下生成物の修正
- `ride_action_boat` テンプレート自体の削除
- `/toc-immersive-ride` の POV コンセプトの撤廃（没入型の定義は維持）

