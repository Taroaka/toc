# Russell Affect Design Handoff Report

## 1. Current Status

この作業では、`output/` 配下のレポート構成には触れていない。

理由:

- ユーザーから、別の AI エージェントが `output/` 内レポート構成を変更中との共有があった
- 衝突回避のため、今回の成果物は repo 側の正本ドキュメントと `.steering/` に限定した

このレポートは、別エージェントへ渡すための単一ハンドオフ文書である。

## 2. User Intent

ユーザー意図は次の 2 点だった。

1. 「ラッセルの感情の円環モデル」について deep research する
2. その調査結果を、現状の物語設計 / 台本設計の参照可能な感情設計レイヤーとして repo に落とし込む

追加意図として、Hollywood 的な感情設計との接続も調査し、
商業映画や現代資本主義的な制作最適化の文脈を踏まえて使えるようにすることが求められた。

## 3. Research Conclusion

### 3.1 Russell model itself

調査結果としては、Russell の円環モデルは「感情カテゴリ一覧」より、
`valence` と `arousal` の 2 軸で affect を位置づける座標系として扱うのが最も正確である。

主要ポイント:

- Russell (1980)
  - affect を `pleasure-displeasure` と `arousal` の 2 軸で整理
- Russell & Barrett (1999)
  - `core affect` を、対象を必ずしも持たない、単純な快/不快と活性/不活性の感じとして整理
- Russell (2003)
  - 離散感情は `core affect` に解釈・帰属・行動準備などが重なって成立すると再定式化

設計上の含意:

- `curiosity`, `awe`, `dread`, `relief` などのラベルだけでは曖昧さが残る
- その下に `valence / arousal` を置くと、scene 単位で感情目標を比較しやすくなる

### 3.2 Hollywood / capitalism connection

公開情報ベースでは、
`Hollywood の writer's room が Russell を明示的な標準教科書として採用している`
とまでは言えない。

ただし、次の意味ではユーザーの見立てはかなり妥当である。

- emotional arc の商業分析が進んでいる
- trailer 編集では arousal 設計が実証研究されている
- 観客反応予測や greenlight 支援に AI / analytics が使われている

より正確な表現:

- `Russell そのものの直接採用` より
- `Russell と同型の valence/arousal 的な感情指標の実務化`

### 3.3 Strongest evidence found

- Del Vecchio et al. (2020)
  - 6,174 本の映画 script / film を emotional arcs で分類
  - `Man in a Hole` が box office と強く結びつくと報告
  - ただし「最も高評価」や「最も芸術的」という意味ではない
- Thomsen & Heiselberg (2020)
  - drama film trailers において、単純な煽り続けではなく `two-peak` の arousal 構造が有効
- 20th Century Fox + Google (2018)
  - trailer の computer vision 分析を通じて audience prediction に機械学習を利用
- Warner Bros. + Cinelytic / ScriptBook 周辺
  - greenlight / packaging / marketing / distribution 支援に predictive analytics が導入されていることを整理したレビューを確認

### 3.4 Practical takeaway for this repo

この repo で使うべき結論は次である。

- `6 arcs` は作品全体の macro 波形として残す
- scene / cut 単位では `valence / arousal` を補助レイヤーとして追加する
- script の正本は `experienced emotion` ではなく `intended affect` とする

## 4. Repo Changes Already Made

今回の作業で、以下の正本ドキュメントと補助文書を更新した。

### 4.1 Added

- `docs/affect-design.md`
  - 新規追加
  - Russell / core affect の要点
  - Hollywood / trailer / analytics との接続
  - repo 内での採用方針
  - `story.md` / `script.md` 契約例
- `.steering/20260411-russell-affect-design/requirements.md`
- `.steering/20260411-russell-affect-design/design.md`
- `.steering/20260411-russell-affect-design/tasklist.md`
- `.steering/20260411-russell-affect-design/handoff-report.md`

### 4.2 Updated

- `docs/root-pointer-guide.md`
  - `Read Next` に `docs/affect-design.md` を追加
- `docs/story-creation.md`
  - 関連ドキュメントに `docs/affect-design.md` を追加
  - 既存の `6 arcs` を macro layer と明示
  - `affect_design.scene_targets[]` を schema に追加
  - 感情設計理論の参考文献を追記
- `docs/script-creation.md`
  - 入力参照に `docs/affect-design.md` を追加
  - scene schema に `affect.intended` を追加
  - `emotional_target` はラベル、`affect.intended` は座標という役割分担を記述
  - `Affect Coordinate Layer` の節を追加
- `workflow/script-template.yaml`
  - scene-level の optional affect target を追加
- `workflow/playbooks/script/hero-journey-beat-first.md`
  - scene ごとの `intended_affect` 仮置きと、peak/release の確認項目を追加

## 5. Intended Contract After This Change

### 5.1 Macro vs micro

- macro
  - `emotional_arc.type`
  - 作品全体の大きな波
- micro
  - `affect_design.scene_targets[]`
  - `script.scenes[].affect.intended`
  - scene / cut ごとの感情目標

### 5.2 Canonical meanings

- `emotional_target`
  - 人間が読みやすいラベル
- `affect.intended.valence`
  - `-1.0 .. 1.0`
- `affect.intended.arousal`
  - `0.0 .. 1.0`
- `label_hint`
  - affect の補助ラベル
- `audience_job`
  - `hook | bond | strain | release | aftertaste`
- `contrast_from_previous`
  - `lift | drop | spike | settle | invert`

### 5.3 Authoring rule

script / story の正本に置くのは `intended affect` のみ。

分けるべき概念:

- `intended`
  - 作者 / 演出が狙う affect
- `expected`
  - 一般的視聴者に起きそうな affect
- `experienced`
  - 個別視聴者が実際に感じた affect

今回の変更は `intended` までで止めている。

## 6. Validation

実行済み:

```bash
python scripts/validate-pointer-docs.py
```

結果:

- `Pointer docs valid.`

## 7. Working Tree Notes

現在の working tree には、今回の作業以外の変更も多数ある。
少なくとも次は今回の作業と無関係であり、巻き込まない方がよい。

- `.claude/settings.json`
- `.gitignore`
- `docs/data-contracts.md`
- `docs/how-to-run.md`
- `docs/orchestration-and-ops.md`
- `scripts/build-clip-lists.py`
- `scripts/generate-assets-from-manifest.py`
- `toc/harness.py`
- `workflow/state-schema.txt`
- `scripts/build-run-index.py`
- `server/`
- `start.sh`
- `toc/run_index.py`
- `.steering/20260411-run-index-numbering/`
- `LINE_BOT_SETUP.md`

別エージェントは、今回の affect design 作業だけを扱うなら、
上記の他変更を revert せず、触れずに進めるのが安全である。

## 8. Suggested Next Work For Other Agents

別エージェントに振るなら、次の 2 系統が自然である。

### Agent A: contract propagation

目的:

- affect layer を `docs` 以外の契約にも反映する

候補:

- `docs/data-contracts.md`
- `workflow/state-schema.txt`
- 必要なら evaluator / review 系の schema

具体作業:

- `story` / `script` / `manifest` / `state` の責務境界に affect field をどう残すか整理
- `intended affect` を downstream でどう参照するかを定義

### Agent B: runtime / generator integration

目的:

- 実際の生成フローで `affect.intended` を出力・参照させる

候補:

- story writer
- script writer
- evaluator
- scene planner

具体作業:

- scene 生成時に `emotional_target` だけでなく `affect.intended` も埋める
- peak / release の欠落や高 arousal 連打をレビューで検知できるようにする

## 9. Important Cautions

### 9.1 Do not overclaim Hollywood evidence

書き方として避けるべきもの:

- `Hollywood は Russell を標準採用している`
- `Russell が現代映画脚本の公式理論である`

推奨表現:

- `公開情報上、直接採用の証拠は限定的だが、valence/arousal と同型の感情指標は映画産業の分析・編集・予測実務と強く接続している`

### 9.2 Do not replace 6 arcs

今回の変更は置換ではなく追加である。

- `6 arcs`
  - 作品全体の波
- Russell affect layer
  - scene / cut の波

### 9.3 Do not write into output yet

ユーザー共有どおり、`output/` のレポート構成は別エージェントが変更中である。
この affect design の成果物を `output/` 配下へ移すのは、その変更が落ち着いてからでよい。

## 10. Reference Links Used

- Russell (1980), *A circumplex model of affect*
  - https://doi.org/10.1037/h0077714
- Russell & Barrett (1999), *Core affect, prototypical emotional episodes, and other things called emotion*
  - https://emotiondevelopmentlab.weebly.com/uploads/2/5/2/0/25200250/russell_j.a.__barrett_l._f._1999.pdf
- Russell (2003), *Core affect and the psychological construction of emotion*
  - https://cs.uwaterloo.ca/~jhoey/teaching/cs886-affect/papers/Russell-CoreAffect-PsychRev03.pdf
- Posner, Russell, Peterson (2005), *The circumplex model of affect*
  - https://www.psychomedia.it/rapaport-klein/Peterson-05_DevelopPsychopathol10.pdf
- Del Vecchio et al. (2020), *Improving productivity in Hollywood*
  - https://pure-oai.bham.ac.uk/ws/portalfiles/portal/95602489/Del_Vecchio_et_al_2020_Improving_productivity_in_Hollywood_Journal_of_the_Operational_Research_Society.pdf
- Thomsen & Heiselberg (2020), *Arousing the audience*
  - https://doi.org/10.1386/jsca_00013_1
- Google Cloud Blog (2018), *How 20th Century Fox uses ML to predict a movie audience*
  - https://cloud.google.com/blog/products/ai-machine-learning/how-20th-century-fox-uses-ml-to-predict-a-movie-audience
- NECSUS (2020), *Ghost in the (Hollywood) machine*
  - https://necsus-ejms.org/ghost-in-the-hollywood-machine-emergent-applications-of-artificial-intelligence-in-the-film-industry/
- COGNIMUSE (2017), intended / expected / experienced emotion distinction
  - https://link.springer.com/article/10.1186/s13640-017-0194-1

## 11. Minimal Resume Brief

別エージェント向けに最短で言うなら次で足りる。

- Russell の感情円環は `valence / arousal` の座標系として採用
- Hollywood への直接採用断定は避ける
- ただし emotional arc analytics / trailer arousal design / audience prediction との接続は強い
- repo では `6 arcs` を残しつつ、scene-level の `affect.intended` を追加済み
- `output/` は今は触らない
- 次は contract propagation か runtime integration
