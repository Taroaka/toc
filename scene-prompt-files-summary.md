# Scene Prompt Related Files Summary（改善版）

このファイルは、scene / cut / scene image prompt 改善のために参照する既存ファイルと、
それぞれが主に読まれる p 番台をまとめたもの。

今回の改善では、scene を「時間分割」ではなく、**映画の中で観客の理解・感情・期待を変化させる劇的単位**として扱う。
scene の出来が後段の cut、image prompt、motion prompt、narration の品質を決めるため、p400 で scene の劇的責務を固定し、p600 ではそれを“描ける初期状態”へ翻訳する。

---

## 中心ファイル

| ファイル | 主に読まれる番台 | 改善後の役割 |
|---|---:|---|
| `docs/script-creation.md` | `p400` | scene intent / cinematic scene contract / cut blueprint / `visual_beat` / `scene_contract` を作る正本 |
| `docs/implementation/scene-loop.md` | `p400` | scene-set review、per-scene review、cut blueprint review、production readiness gate の正本 |
| `workflow/video-manifest-template.md` | `p400`, `p600`, `p700`, `p800` | `video_manifest.md` の共通テンプレ。scene の意味設計と生成実装をつなぐ正本 |
| `docs/implementation/image-prompting.md` | `p600` | scene/cut contract を、映画的な still prompt と reference 運用へ翻訳するルール |
| `workflow/scene-conte-template.md` | `p400` 補助、場合により `p600` | scene を劇的な cut 列へ分解する橋渡し資料 |

## 補助ファイル

| ファイル | 主に読まれる番台 | 改善後の役割 |
|---|---:|---|
| `workflow/scene-video-manifest-template.md` | scene-series / scene単体 run 用。`p600` 以降 | scene単体を production-ready な manifest にするテンプレ |
| `workflow/scene-outline-template.yaml` | scene-series / bridge 用 | story と generation prompt の間で、scene contract と cut blueprint を保持する outline |
| `workflow/scene-script-template.md` | scene-series 用 | Q&A短尺だけでなく、映画的scene台本として使える最小テンプレ |
| `docs/video-generation.md` | `p800`、ただし p600でも参照あり | still → motion → clip の接続。first/last frame と motion prompt の責務を定義 |
| `docs/implementation/asset-bibles.md` | `p500`, `p600` | character/object/location bible と参照画像の扱い。scene の劇的機能に必要な asset を固定 |

---

## 読む順番

scene の品質を改善する場合は、次の順に読む。

1. `docs/script-creation.md`
   - p400 で scene を「何が変わる場面か」に落とす。
   - `dramatic_question`、`scene_spine`、`value_shift`、`causal_turn`、`visual_thesis`、`handoff_to_next_scene` を固定する。
2. `docs/implementation/scene-loop.md`
   - scene-set → per-scene → cut blueprint の順に review する。
   - scene が単なる説明や綺麗な絵の羅列になっていないかを gate で止める。
3. `workflow/scene-outline-template.yaml` / `workflow/scene-conte-template.md`
   - story から scene/cut へ分解する中間成果物を作る。
4. `workflow/video-manifest-template.md`
   - skeleton manifest に scene/cut の契約を materialize する。
5. `docs/implementation/image-prompting.md`
   - cut の `visual_beat` を、後段動画が始まる直前の映画的 still へ翻訳する。
6. `docs/video-generation.md`
   - still と motion prompt が同じ cut 目的を担っているかを確認する。
7. `docs/implementation/asset-bibles.md`
   - scene をまたいで揺れてはいけない人物・場所・舞台装置を p500 で固定する。

---

## Scene の意義

scene は、物語を単に時間で分割した単位ではない。
scene は、物語全体の中で「観客に何を渡し、何をまだ渡さず、どの感情状態へ移すか」を決める制作単位である。

映画的な scene は、最低限次を持つ。

- **Dramatic Question**: この scene の間、観客が追う問い。例: `彼は真実を見つけるのか`。
- **Pressure**: 人物や状況にかかる圧力。単なる説明ではなく、選択・危険・誘惑・損失がある。
- **Value Shift**: scene の前後で何が変わるか。安心→不安、無知→理解、孤立→接続など。
- **Causal Turn**: 次 scene を発生させる不可逆の変化。発見、決断、失敗、誤解、犠牲など。
- **Visual Thesis**: その scene を代表する画。観客が一枚絵で意味を理解できる visual proof。
- **Handoff**: 次 scene の入口。視線、方向、音、アイテム、未解決の問いでつなぐ。

scene が担う主な役割:

- 物語目的: 出会い、発見、誘惑、対立、変化、帰還、余韻など。
- 情報設計: 観客に渡す情報と、まだ隠す情報を分ける。
- 感情設計: 前 scene から次 scene へ、観客の感情をどう動かすかを決める。
- 視覚設計: p600 の scene image prompt が迷わないよう、何を画として見せるべきかを決める。
- 接続設計: 前後の scene との因果、進行方向、光、場所、人物状態、重要アイテムの連続性を作る。
- 生成実装への橋渡し: p500 asset、p600 image、p700 narration、p800 video に渡す注意点を明確にする。

---

## 映画レベルの scene を作るための最小契約

p400 で各 scene は次の contract を持つ。

```yaml
scene_intent:
  story_purpose: "この scene が物語全体で担う役割"
  dramatic_question: "この scene の間、観客が追う問い"
  scene_spine: "setup → pressure → turn → payoff → handoff の1文要約"
  value_shift:
    from: "scene開始時の価値/感情/関係"
    to: "scene終了時の価値/感情/関係"
    visible_evidence: ["画面だけで変化が読める証拠"]
  causal_turn: "次sceneを発生させる不可逆の出来事/決断"
  audience_information: []
  withheld_information: []
  reveal_constraints: []
  affect_transition: "観客感情の変化"
  visual_thesis: "この scene を代表する一枚絵の考え方"
  handoff_to_next_scene: "次sceneへつなぐ視覚/音/因果のアンカー"
  production_risks: []
  handoff_notes:
    p500_asset: []
    p600_image: []
    p700_narration: []
    p800_video: []
```

p420 で各 cut は次の contract を持つ。

```yaml
cut_blueprint:
  cut_role: "main|sub|transition|reaction|visual_payoff"
  cut_function: "setup|pressure|threshold|turn|payoff|reaction|handoff"
  target_beat: "この cut で伝える1つのこと"
  screen_question: "この cut の間、観客が画面から読む問い"
  visual_beat: "画として何が見えるか"
  must_show: []
  must_avoid: []
  done_when: []
  first_frame_brief: "動画が動き出す直前に見えている初期状態。prompt本文に制作メタは入れない"
  motion_brief: "stillから始まる動き。新しい物語情報を勝手に追加しない"
  narration_role: "setup|fact|emotion|contrast|aftertaste|silent"
  asset_dependency_hint:
    character_ids: []
    object_ids: []
    location_ids: []
    reusable_still_candidates: []
```

---

## NG パターン

- scene が「この情報を説明する」だけで、人物・状況・関係の変化がない。
- scene の目的が「綺麗な背景を見せる」だけで、物語上の圧力や handoff がない。
- 1 cut に reveal、感情反転、場所移動、決断、反応をすべて詰め込む。
- p400 の `generation_prompt` に完成 prompt を書いてしまい、p600 の構造化 review を飛ばす。
- prompt 本文に `scene10_cut01`、`物語「...」の一場面`、`最初の1フレーム` など制作メタを残す。
- `tts_text` を image prompt の主ソースにして、映像がナレーションの説明絵になる。

---

## 他エージェント向け: この repo の動画制作概要

この repo は、ひとつの題材から調査、物語化、scene / cut 設計、画像生成、ナレーション、動画生成、最終レンダリングまでを段階的に進める ToC 動画制作パイプラインである。
目的は、単発の画像や動画クリップを作ることではなく、物語全体の流れ、reveal 順序、感情変化、視覚的な一貫性を保ったまま、生成素材を最終動画へ統合すること。

基本の制作順:

1. `p100 research`: 題材の情報収集を行い、根拠と使える素材を `research.md` に整理する。
2. `p200 story`: 調査結果をもとに、物語全体の構造、scene、テーマ、観客に渡す情報を `story.md` にする。
3. `p300 visual planning`: 必要に応じて `visual_value.md` を作り、映像で強く見せる価値、asset 候補、p400/p500/p600/p700 への handoff を決める。
4. `p400 script`: cinematic scene contract と cut blueprint を作り、`script.md` と skeleton `video_manifest.md` に落とす。ここではまだ本番 prompt や素材生成はしない。
5. `p500 asset`: 繰り返し使う人物、場所、小道具、舞台装置を asset bible / reference image として固定する。
6. `p600 scene/image`: production `video_manifest.md` の scene / cut image prompt を作り、`image_generation_requests.md` を凍結して scene still を生成する。
7. `p700 narration`: 確定した scene image と script を見ながら narration / TTS を作り、尺を確認する。
8. `p800 video`: scene still、motion prompt、必要な first/last frame を使って動画 clip を生成する。
9. `p900 render/qa`: 生成 clip と audio を結合し、最終動画を QA する。

エージェントが守るべき前提:

- `story.md` は物語の正本、`script.md` は scene / cut の意味設計の正本、`video_manifest.md` は生成実装の正本。
- p400 では prompt を完成させず、p600 で image prompt を作る。
- scene image prompt は、その動画を始める初期状態として設計する。ただし prompt 本文に `最初の1フレーム` などの制作メタ情報は書かない。
- 参照画像 path や `scene10_cut01` のような運用メタは prompt 本文に入れず、人物、場所、道具、行為、光、構図、質感として具体化する。
- 生成判断やレビュー結果は、親チャットだけに残さず `video_manifest.md`、request file、review artifact、state に残す。
