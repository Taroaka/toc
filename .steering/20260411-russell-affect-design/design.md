# Design

## Core Principle

感情設計を 2 層に分ける。

- macro arc
  - 作品全体の上がり下がり
  - `rags_to_riches` / `man_in_hole` など
- micro affect
  - scene / cut ごとに今ここで狙う感情
  - Russell 系の `valence` / `arousal` を使う

## Documentation Shape

新しい正本として `docs/affect-design.md` を追加する。

この文書では次を定義する。

- Russell / core affect の最低限の理論
- Hollywood / 映画産業での近接する運用実態
- 本 repo における採用方針
- `intended / expected / experienced` の区別
- `story` / `script` に置く optional field

## Integration Points

- `docs/root-pointer-guide.md`
  - Read Next に `docs/affect-design.md` を追加
- `docs/story-creation.md`
  - 関連ドキュメントに affect guide を追加
  - 6 arcs は macro、Russell は micro という役割分担を追記
  - `story` schema に `affect_design.scene_targets[]` を追加
- `docs/script-creation.md`
  - 台本の schema に scene-level `affect.intended` を追加
  - `emotional_target` はラベル、`affect.intended` は座標と明記
- `workflow/script-template.yaml`
  - scene-level affect target を optional field として追加
- `workflow/playbooks/script/hero-journey-beat-first.md`
  - Scene 割当時に affect target を仮置きする guidance を追加

## Data Contract

数値レンジは実務優先で次にする。

- `valence`: `-1.0 .. 1.0`
  - 負 = aversive / 苦い
  - 正 = pleasant / 好ましい
- `arousal`: `0.0 .. 1.0`
  - 低 = quiet / still
  - 高 = activated / urgent

scene には必要に応じて次を持てる。

```yaml
affect:
  intended:
    valence: 0.2
    arousal: 0.7
    label_hint: "curiosity"
    audience_job: "hook"
    contrast_from_previous: "lift"
```

## Boundary

- 本 repo では Russell を「Hollywood の普遍的標準」とは書かない
- 代わりに「映画産業で実際に使われている近接指標と接続しやすい affect 座標系」として採用する
- 商業最適化だけを目標にせず、創造と選択の両立という repo の既存方針に合わせる
