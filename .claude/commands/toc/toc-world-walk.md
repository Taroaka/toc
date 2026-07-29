# /toc-world-walk

既存 ToC run の `story.md` と `assets/` を参照し、「〇〇の世界観を散歩してみた」形式の観察者 POV 動画を作るコマンド。

## 使い方

```text
/toc-world-walk --source-run output/桃太郎_<timestamp>
```

topic を明示する場合:

```text
/toc-world-walk --source-run output/桃太郎_<timestamp> --topic "桃太郎の世界観を散歩してみた"
```

script / manifest までで止める場合:

```text
/toc-world-walk --source-run output/桃太郎_<timestamp> --stage script --review-policy drafts
```

## コンセプト

- 視点は **観察者POV**。カメラは世界の中を歩くが、主人公本人や参照キャラ本人の視点ではない
- カメラは常に少し遠目。中景〜遠景で、物語を横から見かける
- 派手な演出、急接近、劇的な戦闘強調、カメラの介入はしない
- 序盤に **物語が進まない asset 内散歩** を置く
- 中盤から参照キャラが遠景に現れ、物語がそちらで始まっているのを見かける
- 観察者は物語へ干渉せず、世界観の中を歩き続ける

## 引数

$ARGUMENTS:
- `--source-run output/<topic>_<timestamp>` (required)
- `--topic "<topic>"` (optional, default: `<source topic>の世界観を散歩してみた`)
- `--stage research|story|visual_value|script|asset|scene_implementation|narration|video_generation|render|p100|100|...|p900|900` (optional)
- `--video-tool kling|kling-omni|seedance|veo` (optional, default: `kling-omni`)
- `--review-policy strict|drafts` (optional)

## 実装ヘルパ

```bash
python scripts/toc-world-walk.py --source-run output/<topic>_<timestamp>
```

内部的には `scripts/toc-immersive-ride.py --experience world_walk --source-run ...` を使う。
`--stage` 省略時は、参照元を使う散歩設計の承認境界である `p450`
（script / skeleton manifest）で停止する。フロントの新規作成はこの scaffold
helper ではなく、`toc-immersive-frontend-run.py` の p680 経路を使う。

## 重要なプロンプト要件

### DO

- `観察者POV`
- `少し遠目、中景〜遠景中心`
- `自然な歩行速度、水平線安定、カメラ高さ一定`
- `物語が進まない asset 内散歩`
- `参照キャラが遠景に現れる`
- `物語が別導線で始まっているのを見かける`
- `画面内テキストなし`

### DON'T

- 主人公本人の主観視点
- 自撮り、肩越し密着、顔の大写し
- 急接近、劇的な手持ちブレ
- 派手なエフェクト、爆発や戦闘の強調
- 観察者が物語へ介入する構図
