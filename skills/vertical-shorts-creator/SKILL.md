---
name: vertical-shorts-creator
description: |
  Select high-impact scenes from an approved 16:9 ToC run and prepare the command for a centered 9:16 short.
  Use when: the user asks for a vertical short, short-form recut, highlight clip, or a way to turn an approved horizontal ToC run into a 9:16 short without regenerating scenes.
---

# Vertical Shorts Creator（縦ショート生成）

## Overview

完成・承認済みの run から、60秒の縦ショートを作る。
このスキルは “自動実行” ではなく、**選ぶべき scene と実行コマンド**を出す。

## Preconditions（必須）

- run dir: `output/<topic>_<timestamp>/`
- `state.txt` に `review.video.status=approved` が入っている（人間の最終OK）
- `video.mp4`（または `artifact.video`）が存在する

未承認なら先に承認する:

```bash
python scripts/toc-state.py approve-video --run-dir output/<topic>_<timestamp> --note "OK"
```

## How to choose scenes（刺激強めの選び方）

“刺激”は主観なので、まず候補を10個程度挙げ、最終は人間が選ぶ。
判断の軸（例）:

- 危機/緊張（追跡、落下、爆発、水、怪異）
- 速度/加速度（ライドの加速、カーブ、接近）
- 驚き（巨大物の出現、色/光の急変、急な視点の発見）
- ビジュアルの密度（見せ場ディテール、没入感）
- 1カットで成立する（前後文脈がなくても理解できる）

## Output（作るもの）

1) 推奨 scene_id リスト（合計60秒になるまで）
2) 実行コマンド

```bash
python scripts/make-vertical-short.py \
  --run-dir output/<topic>_<timestamp> \
  --scene-ids 10,20,30,40,50,60,70,80 \
  --duration-seconds 60 \
  --out output/<topic>_<timestamp>/shorts/short01.mp4
```

## Notes

- この方式は “既存の横動画を中心cropして縦化” するため、重要被写体が中央にないsceneは不利。
- うまくいかない場合は scene_id を選び直す（まずはここで反復する）。
