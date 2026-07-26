# Legacy / Non-canonical Multi-agent Immersive Cuts Playbook (ToC)

> **Legacy 専用 / canonical 非対応:** この手順は、semantic scene/cut contract が存在しない旧 `video_manifest.md` を、人手で raw image prompt の固定数 scaffold へ移行する場合だけに使う。`scene_event`、`scene_cut_coverage_plan`、`cut_contract` などを持つ canonical manifest には使用しない。

canonical な新規作成・再設計では、backend の `/api/image-gen/runs/create` または同じ backend create route を呼ぶ次の入口を使う。

```bash
python scripts/toc-create-run-headless.py --title "<title>" --source "<source>" --no-images
```

この legacy tool は canonical projection / review を実装しないため、canonical semantic key を検出したら fail closed で停止する。

目的: 非 canonical な旧 `video_manifest.md` の各 scene に対し、利用者が明示した件数の raw-prompt cut scratch を、衝突なく並列編集する。

## 原則

- 共有ファイル（`video_manifest.md`）は **同時編集しない**（single-writer で統合）。
- 並列化は「scene別 scratch」→「1人がマージ」で実現する。

## ファイル構成（run dir）

`output/<topic>_<timestamp>_immersive/`
- `video_manifest.md`（正本 / single-writer が更新）
- `state.txt`（必要なら single-writer が更新）
- `scratch/cuts/sceneXX.yaml`（scene担当が編集 / scene単位で競合しない）

## Phase 0: Prepare scratch（直列）

single-writer が scratch 雛形を作る:

```bash
python scripts/ai/toc-immersive-cuts-multiagent.py \
  --run-dir "output/<topic>_<timestamp>_immersive" \
  --legacy-fixed-cut-scaffold \
  --cut-count "<sceneごとに作る明示件数>"
```

`--cut-count` に暗黙値はない。物語や尺から semantic cut 数を導出する機能ではなく、legacy scaffold に作る件数を利用者が明示するための引数である。

## Phase 1: Per-scene cuts design（並列）

scene担当者は、自分の scene の scratch だけ編集して cuts を決める:

- 例: `scratch/cuts/scene02.yaml`
  - cuts 数: Phase 0 で明示した件数。各 scene scratch は非空にする
  - `image_generation.prompt` は **日本語**で書く（ユーザーが修正しやすいように）。必要なら生成モデル向けに重要英単語を併記してよい
  - `image_generation.prompt` は cut ごとに目的（構図/アクション/役割）を変える
  - `image_generation.output` は衝突しない命名にする（推奨: `assets/scenes/scene02_cut01.png`）

## Phase 2: Merge to manifest（直列）

single-writer が scratch を manifest へ統合:

```bash
python scripts/ai/merge-immersive-cuts.py \
  --run-dir "output/<topic>_<timestamp>_immersive" \
  --legacy-fixed-cut-scaffold
```

merge は非空の任意 cut 件数を受け入れる。旧運用との互換確認が必要な場合に限り `--min-cuts <n>` / `--max-cuts <n>` を明示できるが、これらは物語設計の規範ではない。不正な YAML、空 cuts、未記入 prompt、manifest に存在しない scene などは、対象ファイルと理由を表示して失敗する。

## Phase 3: Next（ユーザーが起動）

統合が終わったら、次を起動して生成へ進む:

```bash
scripts/toc-immersive-ride-generate.sh --run-dir "output/<topic>_<timestamp>_immersive"
```
