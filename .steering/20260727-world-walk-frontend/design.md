# Design: World Walk Frontend Create

## API

- `GET /api/image-gen/runs/world-walk-sources`
  - `output/` 直下を走査し、p650 契約を満たす非 symlink run のみ返す。
- `POST /api/image-gen/runs/create-world-walk`
  - `source_run_id`, optional title, target duration を受ける。
  - 通常 create と同じ job limit、execution lease、process store、status polling 契約を使う。

## Runtime

通常 create と同じ backend 直下の `scripts/toc-immersive-frontend-run.py`
実行経路を使い、`experience=world_walk`, canonical な `source_run`,
`target_duration_seconds` を渡す。nested app-server 経路は使わない。

参照元は repo の `output/` 直下だけを許可し、`story.md` と `assets/` 配下の
symlink を拒否する。POST 時だけでなく非同期 job 開始時にも再検証する。

## Frontend

既存の作成モードへ `world_walk` を追加する。選択時だけ参照元一覧を取得し、
参照元 selector と読み取り専用 path を表示する。既定タイトルは placeholder と
backend fallback で扱い、参照元を切り替えても古いタイトルを state に残さない。
