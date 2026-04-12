# Design

- `generate-assets-from-manifest.py` が `script.md` を読み、selector ごとの preferred visual beat map を作る
- preferred visual beat は `human_review.approved_visual_beat || visual_beat`
- scene image request のみを対象にし、asset request と video request には影響させない
- 現段階では scene 7 以降の request だけに script visual beat を優先反映する
- 反映方法は request prompt の先頭へ `[場面の核]` ブロックとして追加する
- 既存 prompt に同じ文面がすでに含まれている場合は重複追加しない
- docs には `script.md` 優先を明記する
