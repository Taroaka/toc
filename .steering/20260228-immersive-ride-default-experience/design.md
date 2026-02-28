# /toc-immersive-ride: Default experience switch (design)

## Approach

1) **Default を `cloud_island_walk` に変更**
   - `scripts/toc-immersive-ride.py` の `--experience` default を `cloud_island_walk` にする
   - `.claude/commands/toc/toc-immersive-ride.md` / `docs/implementation/immersive-ride-entrypoint.md` / `.claude/agents/immersive-scriptwriter.md` の default 表記を揃える

2) **`ride_action_boat` を legacy / optional として位置づけ**
   - 「ボート/安全バー/手元アンカー」を *選択した experience* の固定条件として明確化する（デフォルト要件ではない）

3) **年齢固定（例: 20代）を撤去**
   - `ride_action_boat` の統一要素は「人間の手（年齢/性別は作品側で必要なら指定）」とし、固定の年齢記述を消す

4) **画像プロンプトの “一般例” を中立化**
   - `docs/implementation/image-prompting.md` の一般セクションで `hands+bar` 等の具体例を「アンカーの例」として扱い、通常 run / scene-series に波及しないことを明記する

## Rationale

- default を変えることで、今後の新規生成（明示指定なし）で `ride_action_boat` の固定条件が混入しない
- `ride_action_boat` は残すため、過去 run の再現や特定の没入型演出が必要な場合に後方互換を維持できる
- 年齢指定は作品要件になり得るが、テンプレの固定条件としては不要で誤解を生むため撤去する

## Compatibility

- 明示的に `--experience ride_action_boat` を指定した場合のみ、従来のボート/安全バー/手元アンカーの固定条件を採用する
- 既存のテンプレファイル（`workflow/immersive-ride-video-manifest-template.md`）は保持する

