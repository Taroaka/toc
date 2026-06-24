# Frontend Create Storyboard Mode Requirements

## Goal

フロントの新規 ToC 作成モーダルに作成モードを追加し、通常作成と `1scene=1ストーリーボード式` を選べるようにする。

## User-Approved Decisions

- 通常モードは既存の `/api/image-gen/runs/create` へ今までと同じ request を送る。
- `1scene=1ストーリーボード式` は新 endpoint を使う。
- `1scene=1ストーリーボード式` の新規 run folder は通常版と区別できるよう、title slug に `_storyboard` を足す。
- 新モードでも scene / cut の生成と各 cut 画像生成までは通常フローと同じ。
- 各 cut の単体画像は残す。
- 各 scene につき `assets/storyboards/sceneXX_storyboard.png` を作り、cut 画像を1枚のストーリーボード画像にまとめる。
- 動画生成自体は実行しない。
- p680 まで到達し、`video_manifest.md` と `video_generation_requests.md` が scene storyboard を動画入力にする形になっている。
- 実画像ありで作成し、cut 画像生成は Codex image generation を使う。

## Scope

- Frontend: `server/web/src/main.tsx`
- Backend API/orchestration: `server/image_gen_app.py`
- Focused tests: `tests/test_image_gen_server.py`
- Docs/checklist: `.steering/20260613-frontend-create-mode-storyboard/`

## Non-Goals

- 通常 endpoint の request shape を変更しない。
- 動画生成 provider を実行しない。
- scene / cut 設計、semantic QA、p680 image review gate を迂回しない。
- cut 単体画像を削除したり、cut-level artifact を storyboard で置き換えたりしない。
- 既存 run folder を rename しない。

## Done When

- 新規作成モーダルに `通常` と `1scene=1ストーリーボード式` のプルダウンがある。
- `通常` 選択時は既存 `/api/image-gen/runs/create` に既存 body を送る。
- `1scene=1ストーリーボード式` 選択時は新 endpoint に送る。
- `1scene=1ストーリーボード式` の run folder は `<title>_storyboard_YYYYMMDD_HHMM` になる。
- 新 endpoint は通常 p680 フローを実行した後、各 scene の cut 画像から `assets/storyboards/sceneXX_storyboard.png` を作る。
- 新 endpoint は `video_manifest.md.scenes[].render_units[]` と `video_generation_requests.md` を scene storyboard 入力の動画 request として materialize する。
- p680 image review handoff は維持され、動画生成は開始されない。
- Focused backend tests と frontend build/typecheck が通る。
