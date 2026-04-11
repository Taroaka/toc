# Script Method: Hero Journey Beat First

## Use when
- 物語の骨格を崩さず、sceneごとの感情カーブを明確にしたいとき

## Task structure (2-stage)

### Stage 1: Draft 
1. `research.story_baseline.beat_sheet` を scene へ割当
2. opening/development/turn/climax/ending に再編
3. 各sceneに `narration` / `visual` / `research_refs` を埋める
4. 各sceneに `intended_affect`（最低でも `label_hint`、可能なら `valence/arousal`）を仮置きする
5. まずは通しで読める `story.md` を作る（完璧を目指さない）

### Stage 2: Polish (英雄の旅で推敲)
1. 下記チェックで「英雄の旅」に沿っているか確認する
2. 弱い箇所を scene 単位で書き直す（不足要素を補強）
3. 感情カーブが前半→中盤→後半で自然につながるよう調整する
4. `valence/arousal` の変化が唐突すぎないか、必要な peak/release が置けているか確認する
5. 文章を読み手目線で磨く（冗長削減、論理飛躍修正）

## Hero Journey check (推敲用)
- Call to Adventure: 冒険への呼びかけが明確か
- Threshold Crossing: 境界越えが scene で可視化されているか
- Trials/Allies: 試練・協力者が機能しているか
- Ordeal/Climax: 最大試練が物語上の必然になっているか
- Return/Aftermath: 帰還または帰還不能の帰結が主題に接続しているか

## Quality gate (人が見れる品質)
- 読んで「何が起きたか」が一読で追える
- 各sceneの役割が重複しすぎていない
- `research_refs` が主要sceneに紐づいている
- `intended_affect` が scene の仕事と一致している
- 結末が `governing_thought` と矛盾しない

## Output contract
- `story.md` の `script.scenes[]`（Stage 1）
- `story.md` の推敲版（Stage 2）
- 各sceneに `scene_id` と `research_refs`
