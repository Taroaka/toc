---
name: frontless_review
description: ToCの設計変更後に、フロントUIを介さず、フロント作成ボタンと同じbackend create routeで物語生成を実行し、修正の再現性と設計反映を検証する。scene/cut/prompt設計、cut_contract、画像生成有無の回帰確認時に使用。
---

# frontless_review

## Overview

このスキルは、ToCの設計や生成プロンプトを更新したあと、フロントエンド画面を操作せずに新規runを作成し、変更が実際の生成ルートに反映されているか確認するための手順です。

重要なのは、フロントUIを使わないだけで、作成ルート自体はフロントと同じにすることです。つまり、`scripts/toc-immersive-frontend-run.py` を主入口として直接叩くのではなく、フロントの作成ボタンと同じ `/api/image-gen/runs/create` backend endpoint を通します。

## Why This Matters

ToCの設計改善は、ドキュメントやテンプレートを直しただけでは十分ではありません。実際の新規run作成で、修正が story / script / video_manifest / image_generation_requests / video_generation_requests に反映され、レビューが求める状態になっているかを確認する必要があります。

この検証により、次を確認します。

- 修正の再現性: 新しいrunを1から作っても同じ設計方針が反映されるか。
- ルート同一性: フロント作成ボタンと同じbackend endpointを通っているか。
- 設計反映: `cut_contract`、`first_frame_contract`、`motion_contract`、review gateが成果物に入るか。
- 責務分離: p600画像requestに `motion_brief` が漏れず、p800動画requestには `motion_brief` が入るか。
- 回帰検知: scene数、cut数、handoff、no-reference laneなど既存品質条件が壊れていないか。

## When to Use

次の状況で使います。

- ToCのscene/cut/prompt設計を変更したあと。
- `toc/review_loop.py`、`toc/stage_evaluator.py`、`scripts/generate-assets-from-manifest.py`、`scripts/toc-immersive-frontend-run.py` を変更したあと。
- フロントから毎回手動でシンデレラを作る代わりに、同じ作成ルートでヘッドレス検証したいとき。
- `cut_contract` や `motion_brief` 分離が新規runに反映されているか確認したいとき。

## Execution Function

基本の実行関数はこれです。

```bash
python scripts/toc-create-run-headless.py \
  --title "シンデレラ" \
  --source "シンデレラ" \
  --no-images
```

画像生成はデフォルトで有効です。設計・manifest・requestだけを速く確認したい場合だけ `--no-images` を付けます。

画像生成まで含めて、フロント作成に近い重い検証を行う場合:

```bash
python scripts/toc-create-run-headless.py \
  --title "シンデレラ" \
  --source "シンデレラ"
```

既にbackend serverを起動している場合は、実サーバーのendpointへ投げます。

```bash
python scripts/toc-create-run-headless.py \
  --title "シンデレラ" \
  --source "シンデレラ" \
  --base-url "http://127.0.0.1:8000" \
  --no-images
```

## Required Review Checks

実行後、最低限次を確認します。

```bash
python scripts/toc-create-run-headless.py \
  --title "シンデレラ" \
  --source "シンデレラ" \
  --no-images \
  --assert-profile cut_contract_v2
```

確認対象:

- `output/<run_id>/logs/regression/headless_regression_report.md`
- `output/<run_id>/story.md`
- `output/<run_id>/script.md`
- `output/<run_id>/video_manifest.md`
- `output/<run_id>/image_generation_requests.md`
- `output/<run_id>/video_generation_requests.md`
- `output/<run_id>/logs/eval/cut_blueprint/round_01/aggregated_review.md`

合格条件:

- create jobが `completed`。
- `video_manifest.md` の各cutに `cut_contract` がある。
- `first_frame_contract.first_frame_brief` がある。
- `motion_contract.motion_brief` がある。
- `image_generation_requests.md` に `motion_brief` / `motion_contract` が漏れていない。
- `video_generation_requests.md` には動画生成用のmotion情報がある。
- scene数が最低限の物語構造を満たす。シンデレラなら5 sceneで終わらせない。

## What Not To Do

してはいけない行動:

- フロントUIを手で操作して検証を代替する。
- 主検証として `scripts/toc-immersive-frontend-run.py` を直接叩く。
- `story.md`、`script.md`、`video_manifest.md` を手で後処理して、作成ルートの失敗を隠す。
- `output/<run_id>` の既存成果物を再利用して、新規生成の再現性確認を省略する。
- `/api/image-gen/runs/create` を通らない独自ショートカットを「フロントと同じルート」とみなす。
- 画像生成なし検証をしたいだけなのに、フロントやサーバー再起動を必須にする。
- `reference_count == 0` の画像requestを `standard` laneに変更する。no-reference requestは `execution_lane=bootstrap_builtin` のままにする。
- p600画像promptに `motion_brief` を混ぜる。

## Guidelines

- 通常は `--no-images` で高速に設計反映を確認する。
- 画像品質や参照DAGまで見たい時だけ、`--no-images` を外して重い検証を行う。
- 失敗時は `logs/regression/headless_regression_report.md` と `logs/app_server/` を先に読む。
- 修正したら、同じコマンドで新しいrunを作り直す。既存runの手修正で合格扱いにしない。
- 結果報告では、run dir、report path、失敗assertion、次に直すべき設計箇所を短く示す。

## Example Report

```text
frontless_review 実行結果:
- run_dir: output/シンデレラ_20260524_1200
- report: output/シンデレラ_20260524_1200/logs/regression/headless_regression_report.md
- status: passed
- 確認: cut_contractあり、画像requestにmotion_brief漏れなし、動画requestにmotionあり
```

