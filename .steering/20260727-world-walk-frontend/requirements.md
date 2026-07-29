# Requirements: World Walk Frontend Create

## Goal

Image generation app の新規作成モーダルから、既存の完成済み ToC run を参照して `world_walk` run を作成できるようにする。

## Success Criteria

- 作成モードに「世界観散歩」が表示される。
- 選択時に `GET /api/image-gen/runs/world-walk-sources` から参照可能な完成済み run を選べる。
- `POST /api/image-gen/runs/create-world-walk` が `experience=world_walk` と `source_run=output/<run_id>` を制作経路へ渡す。
- タイトル未入力時は `<参照元タイトル>の世界観を散歩してみた` を使う。
- 通常・ストーリーボード式の既存作成経路を変更しない。
- symlink、output 外、未完成の run は参照元にできない。

## Scope

- `server/image_gen_app.py`
- `server/web/src/main.tsx`
- `tests/test_image_gen_server.py`
- world walk の既存 command / template / docs

