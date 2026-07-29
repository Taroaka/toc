# Requirements: World Walk Command

## Goal

既存の ToC run で作成済みの物語・asset を参照し、「<topic> の世界観を散歩してみた」形式の観察者 POV 動画を作る入口を追加する。

## In Scope

- 新しい slash command `/toc-world-walk`
- 既存 `toc-immersive-ride` フローで使える `world_walk` experience
- `world_walk` 用の `video_manifest.md` テンプレ
- 既存 run の `story.md` / `assets/` を source として記録する scaffold 引数
- docs / agent guide / tests の更新

## Out of Scope

- 外部画像・動画・TTS API の呼び出し変更
- 既存 run の asset を自動コピーする実処理
- 既存 `cinematic_story` / `cloud_island_walk` の挙動変更

## Success Criteria

- `scripts/toc-immersive-ride.py --experience world_walk --source-run output/<run> ...` で `video_manifest.md` に `experience: "world_walk"` と source run / assets が反映される
- `world_walk` は `--source-run` 未指定なら失敗する
- `scripts/toc-world-walk.py --source-run output/<run> ...` で同じ scaffold を作れる
- `/toc-world-walk` command doc が、観察者 POV・遠目・派手な演出なし・途中から参照キャラが遠景に出る構成を明示する

