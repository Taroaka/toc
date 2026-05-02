# Affect Design

## Goal

`6 arcs` だけでは、scene / cut ごとの感情設計には粗すぎる。

このドキュメントは、既存の物語アーク設計を残したまま、Russell 系の `valence / arousal` を使って
「今この瞬間に視聴者へどう感じてほしいか」を設計するための補助レイヤーを定義する。

## 位置づけ

- macro arc
  - 作品全体の感情の大きな上下
  - 例: `man_in_hole`, `icarus`
- micro affect
  - scene / cut 単位の狙い
  - 例: `curiosity`, `dread`, `relief`, `awe`

この repo では、

- `6 arcs` = 長い波形
- Russell / core affect = 短い波形

として併用する。

## Research Summary

### 1. Russell / core affect は「感情カテゴリの辞書」ではなく座標系

Russell (1980) は affect を `pleasure-displeasure` と `arousal` の 2 軸で整理し、
感情語が円環状に並ぶことを示した。

Russell & Barrett (1999), Russell (2003) では、これは `core affect` として整理され、
怒り・恐怖・悲しみのような離散感情は、core affect に文脈解釈・帰属・行動準備などが重なって成立するとされる。

設計上の含意:

- `curiosity` や `awe` はラベル
- その下にある `快-不快` と `活性-静穏` を指定すると scene 設計がブレにくい

### 2. Hollywood で Russell が明示標準だと断定する証拠は弱い

少なくとも公開情報ベースでは、「Hollywood の writer's room が Russell を共通教科書として使っている」
とまでは言えない。

ただし、近接する実務はかなり強い。

- Del Vecchio et al. (2020)
  - 6,174 本の produced movie scripts / films を 6 emotional arcs に分類
  - `Man in a Hole` は box office と強く結びついた
  - ただし IMDb rating が最も高いという意味ではない
- Thomsen & Heiselberg (2020)
  - drama film trailers では「全体的に煽る」より、変化と build-up を持つ `two-peak` arousal 構造が有効
- 20th Century Fox + Google
  - trailer を computer vision で分析し、どの観客層が反応しそうかを予測
- Warner Bros. + Cinelytic / ScriptBook 周辺
  - greenlight / packaging / marketing / distribution の意思決定支援に AI / predictive analytics が導入されている

要するに、現代の映画産業では「感情」は曖昧な芸術語としてだけでなく、
選別・予測・編集・販売の指標として扱われている。

この意味で、「現代資本主義の Hollywood の感情設計」という見立てはかなり妥当だが、
正確には `Russell の教科書的採用` より `Russell と同型の affect 指標の実務化` と表現した方がよい。

## Repo Policy

### 正本にするのは intended affect

脚本段階で管理するのは `intended` のみ。

- `intended`
  - 作者 / 演出が狙う affect
- `expected`
  - 平均的な視聴者に起きそうな affect
- `experienced`
  - 実際の視聴者個人が感じた affect

映画研究でもこの 3 つは分けて扱われる。
script / story の正本は `intended` であり、`experienced` を script に逆流させない。

### 商業最適化と創造性は分けて扱う

感情波形は参考にするが、

- `box office が強いから採用`
- `高 arousal を連打すれば勝つ`

のような短絡はしない。

この repo の方針は引き続き

- 創造 (`Creation`)
- 選択 (`Selection`)

の両立であり、affect layer は選択精度を上げるための補助輪として使う。

### Affect は evidence ではない

affect label や valence / arousal は、視聴体験を設計するための創作・演出上の意図であり、事実根拠そのものではない。
selection や revision の判断材料には使えるが、research grounding、human approval gate、documented uncertainty を上書きしない。

## Affect Scale

### Numeric range

- `valence`
  - `-1.0` = 強い不快 / 喪失 / 嫌悪
  - `0.0` = 中立
  - `1.0` = 強い快 / 喜び / 安堵
- `arousal`
  - `0.0` = 静穏 / 鎮静 / 余韻
  - `0.5` = 中程度の緊張 / 注意
  - `1.0` = 高活性 / 切迫 / 興奮

数値は絶対値ではなく、前後 scene との相対差が重要。

### Quick map

| label | valence | arousal | 用途 |
|------|---------|---------|------|
| curiosity | `0.1 - 0.3` | `0.5 - 0.7` | opening の問い |
| awe | `0.5 - 0.8` | `0.5 - 0.8` | reveal / scale 感 |
| serenity | `0.5 - 0.8` | `0.1 - 0.3` | 休息 / 帰還 |
| dread | `-0.6 - -0.3` | `0.6 - 0.9` | 予兆 / suspense |
| grief | `-0.9 - -0.5` | `0.2 - 0.5` | 喪失 / 代償 |
| panic | `-1.0 - -0.7` | `0.9 - 1.0` | crisis |
| relief | `0.2 - 0.6` | `0.1 - 0.3` | release / aftermath |

## Scene Design Heuristics

### 1. 高 arousal を貼り続けない

高 arousal は効くが、連続すると鈍る。

- peak の価値は contrast で決まる
- 緊張の後に release を置く
- trailer 的な peaks と本編の波形を混同しない

### 2. shock は 2 軸を動かし、clarification は 1 軸だけ動かす

- shock
  - `valence` と `arousal` を同時に大きく動かす
- clarification
  - 片軸中心で十分
  - 例: 不安のまま arousal だけ下げて「理解」に移す

### 3. scene の仕事を affect で言い換える

- `hook`
  - 視線をつかむ
- `bond`
  - 人物に寄る
- `strain`
  - 緊張を蓄積する
- `release`
  - いったん解く
- `aftertaste`
  - 意味や代償を残す

### 4. 終盤は valence より arousal の落とし方が重要

climax 後に何を残すかは、`良い終わりか悪い終わりか` より
`どの速度で静けさに戻すか` の方が効くことが多い。

例:

- happy end
  - 正の valence を保ったまま arousal を落とす
- bittersweet
  - valence を少し負側へ戻しつつ arousal を落とす
- tragic
  - 負の valence のまま静かな余韻へ沈める

## Contracts

### story.md

```yaml
emotional_arc:
  type: "man_in_hole"
  tension_peaks:
    - position_percent: 25
      intensity: 7
      description: "first reversal"

affect_design:
  model: "russell_valence_arousal"
  scene_targets:
    - scene_id: 1
      valence: 0.2
      arousal: 0.7
      label_hint: "curiosity"
      audience_job: "hook"
    - scene_id: 4
      valence: -0.7
      arousal: 0.9
      label_hint: "panic"
      audience_job: "strain"
    - scene_id: 8
      valence: 0.3
      arousal: 0.2
      label_hint: "relief"
      audience_job: "aftertaste"
```

### script.md

```yaml
scenes:
  - scene_id: 3
    narrative:
      phase: "ordeal"
      emotional_target: "dread"
    affect:
      intended:
        valence: -0.5
        arousal: 0.8
        label_hint: "dread"
        audience_job: "strain"
        contrast_from_previous: "spike"
```

`emotional_target` は人間が読みやすいラベル、
`affect.intended` は比較可能な座標、として使い分ける。

## Sources

- [Russell (1980) A circumplex model of affect](https://doi.org/10.1037/h0077714)
- [Russell & Barrett (1999) Core affect, prototypical emotional episodes, and other things called emotion](https://emotiondevelopmentlab.weebly.com/uploads/2/5/2/0/25200250/russell_j.a.__barrett_l._f._1999.pdf)
- [Russell (2003) Core affect and the psychological construction of emotion](https://cs.uwaterloo.ca/~jhoey/teaching/cs886-affect/papers/Russell-CoreAffect-PsychRev03.pdf)
- [Posner, Russell, Peterson (2005) The circumplex model of affect](https://www.psychomedia.it/rapaport-klein/Peterson-05_DevelopPsychopathol10.pdf)
- [Del Vecchio et al. (2020) Improving productivity in Hollywood](https://pure-oai.bham.ac.uk/ws/portalfiles/portal/95602489/Del_Vecchio_et_al_2020_Improving_productivity_in_Hollywood_Journal_of_the_Operational_Research_Society.pdf)
- [Thomsen & Heiselberg (2020) Arousing the audience](https://doi.org/10.1386/jsca_00013_1)
- [Google Cloud Blog (2018) How 20th Century Fox uses ML to predict a movie audience](https://cloud.google.com/blog/products/ai-machine-learning/how-20th-century-fox-uses-ml-to-predict-a-movie-audience)
- [NECSUS (2020) Ghost in the (Hollywood) machine](https://necsus-ejms.org/ghost-in-the-hollywood-machine-emergent-applications-of-artificial-intelligence-in-the-film-industry/)
- [COGNIMUSE (2017) intended / expected / experienced emotion annotations](https://link.springer.com/article/10.1186/s13640-017-0194-1)
