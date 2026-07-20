# Scene Production Method: First Last Frame Continuity

## Use when
- scene間の連続性（継ぎ目）を重視して生成したいとき

## Steps
1. 各sceneの静止画を一貫条件で生成する
2. `scene_n.png -> scene_n+1.png` で動画を生成する
3. chaining frame を保存後、次clipを再materialize・再review・再approveして first frame に使う（provider実行中の動的差し替えは禁止）

## Output contract
- `assets/scenes/sceneN.png`
- `assets/scenes/sceneN_to_sceneN+1.mp4`
- continuityログ（任意）
