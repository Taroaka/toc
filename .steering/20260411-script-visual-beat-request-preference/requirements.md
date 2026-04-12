# Requirements

- scene image request の本文生成では `script.md` を優先参照する
- `script.md` に `human_review.approved_visual_beat` があれば最優先で使う
- `approved_visual_beat` がなければ `visual_beat` を使う
- 既存 docs や旧ロジックに `story.md` 参照が残っていても、scene image request の場面定義は `script.md` を優先する
- 現 run では scene 7 以降の request をまず改善対象にする
- API は呼ばず、request file の materialize だけで確認できること
