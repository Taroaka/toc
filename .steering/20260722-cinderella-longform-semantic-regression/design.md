# Cinderella long-form semantic regression design

## Root cause

8 つの canonical scene を 600 秒用の 15 runtime scene に広げる際、各 sibling に canonical multi-location route 全体を複製している。inactive location は route-only placeholder になり、semantic repair がそれを具体化すると sibling scene が同じ移動を再走する。さらに均等割当が finale を 1 scene のまま残し、探索から身元確認までを 40 秒へ過積載する。

## Design

1. Runtime scene 数を canonical scene の semantic workload に配分し、Cinderella の finale に複数 scene を確保する。
2. Split canonical scene の route は sibling 全体で順序を保ちながら担当区間へ投影する。境界 location の継続は許可するが、完了済み route の原点へ戻さない。
3. 各 runtime route には active authored action を持つ segment だけを残し、route-only / no-root-action placeholder を禁止する。
4. Finale 前半は王宮命令、探索、義姉たちの不適合と排除まで、後半は使者の介入、シンデレラの試着、公的確認を担当する。
5. Tests は scene 数だけでなく aggregate route order、placeholder 不在、隣接 scene の非回帰、finale event allocation を検証する。

## Compatibility

- 300 秒の 8 canonical scene は現行 route を維持する。
- generic story の allocation は既存挙動を維持する。
- 既存 run は書き換えない。
- semantic gate は弱めず、生成物側を修正する。

