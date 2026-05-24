# Agent Roles & Prompts（正本）

このドキュメントは `.steering/20260117-agent-roles/` で合意した内容を **恒久仕様として昇華**したもの。

## 目的

役割単位で責務を分離し、再現性の高い出力と検証可能性を確保する。

## 実行モデル

- 起点は Codex 主軸の assistant command（Claude Code slash command 互換も維持）
- ToC run 全体は L1 Run Orchestrator / L2 P-Bucket Supervisor / L3 Task-Review Agent の3階層で動く
- `state.txt` と `p000_index.md` は append/update されるが、書き手は run 全体で1人ではなく、担当 `p100` 番台の L2 supervisor が bucket single writer として更新する
- 役割別の振る舞いはこのドキュメントと stage readset を正本にし、Claude Code 互換の agent pack は `.claude/agents/*.md` に置く（例: `director`）

## 役割と責務

### Run Orchestrator（L1 / run-level manager）
- 入力: user request / stop target / `state.txt` / `p000_index.md` / `logs/orchestration/pXXX.supervisor_result.json`
- 出力: P-Bucket Supervisor task packet / `logs/orchestration/l2_supervisor_progress.md` progress memo / run-level stop decision / blocked decision
- 参照: `docs/root-pointer-guide.md` / `docs/system-architecture.md` / `docs/data-contracts.md`
- 責務:
  - `p100`-`p900` の依存順序、review policy、approval gate を管理する
  - coarse stop target（例: `p600` -> `p680`）を解決し、必要な bucket だけを順番に起動する
  - 各 `p100` 番台の L2 supervisor を fresh context で起動し、完了まで待つ
  - L2 supervisor 起動時に `logs/orchestration/l2_supervisor_progress.md` へ `invoked` event を追記する
    - 推奨コマンド: `python scripts/record-l2-supervisor-progress.py --run-dir <run_dir> --bucket p600 --event invoked --stop-slot p680`
  - L2 supervisor が返った直後に `returned|blocked|failed` event と result path を同じ progress memo / `state.txt` へ追記する
    - 推奨コマンド: `python scripts/record-l2-supervisor-progress.py --run-dir <run_dir> --bucket p600 --event returned --stop-slot p680 --result logs/orchestration/p600.supervisor_result.json`
  - bucket 完了時は supervisor result、required artifact existence、terminal slot state だけを検証する
  - human review、frontend handoff、hybridization approval を自動承認しない
- 禁止:
  - bucket output の本文 artifact（`research.md`, `story.md`, `script.md`, `video_manifest.md` など）を次 bucket 判定のために読む
  - L2 supervisor の代わりに canonical artifact を統合する
  - L3 critic / aggregator report を直接読んで修正採否する
  - L3 task / review agents の呼び出しを run-level progress memo に記録する
  - 親会話だけにある未記録文脈を次 bucket へ渡す

### P-Bucket Supervisor（L2 / bucket single writer）
- 入力: L1 task packet / bucket stop slot / upstream artifact paths / stage readset
- 出力: canonical artifact updates / `state.txt` slot updates / `p000_index.md` refresh / `logs/orchestration/pXXX.supervisor_result.json`
- 参照: `docs/system-architecture.md` / `workflow/stage-grounding.yaml` / bucket 対応 stage docs
- 責務:
  - 担当 `p100` 番台内では single writer として動く
  - `prepare-stage-context.py` または同等の grounding preflight で readset を確定する
  - L3 task/review agents に渡す入力を artifact path / 目的 / 出力先へ限定する
  - L3 の draft / audit / review / scratch output を読み、担当 bucket の canonical artifact へ採用する差分を選ぶ
  - authoring 直後の review slot では、最大 5 round の evaluator-improvement loop を管理する
  - 各 round で 5 critic agents と 1 aggregator agent を isolated output に限定して起動する
  - aggregator report のうち採用する修正だけを canonical artifact へ反映し、次 round / gate close / human handoff を決める
  - `state.txt` と `p000_index.md` を append / update し、bucket verifier へつなぐ
  - bucket 完了時に supervisor result JSON を書いて L1 に戻す
- 禁止:
  - 他 bucket の canonical artifact を編集する
  - L1 に本文 artifact の精読を要求する
  - hybridization や human review を自動承認する
  - `state.txt` の置き換えや final status の丸投げを行う

### Task / Review Agent（L3 / isolated worker）
- 入力: artifact path / readset path / 目的 / isolated output path
- 出力: `scratch/`, `logs/`, review artifact, generated media, or explicit report
- 責務:
  - research scout、story candidate、visual audit、scene/cut worker、critic、aggregator、grounding auditor、image/video/narration reviewer などを担当する
  - 親会話の未記録文脈に依存しない
  - canonical artifact 更新が必要な場合は patch brief / finding / scratch draft として L2 に返す
- 禁止:
  - canonical artifact、`state.txt`、`p000_index.md` を直接編集する
  - L1 へ直接 handoff する
  - approval gate を確定する

### P-Bucket Supervisor Map

| Bucket | Supervisor owns | Typical L3 agents |
| --- | --- | --- |
| `p100` Research | `research.md`, research review, source trace, slot state | research scouts, grounding auditor, research critics |
| `p200` Story | `story.md`, hybridization gate preparation, story review | Director, story candidates, source-vs-creative auditors |
| `p300` Visual Planning | `visual_value.md`, p400/p500/p600/p700 handoff appendix | Visual Value Ideator, payoff/anchor/risk auditors |
| `p400` Script | `script.md`, `scene_conte.md`, skeleton `video_manifest.md`, p400 review loops | Immersive Scriptwriter, scene workers, scene count coverage / dramatic structure / reveal order / duration density / visual production / handoff critics, production readiness council |
| `p500` Asset | `asset_inventory.md`, `asset_plan.md`, asset requests, reusable asset generation | asset planners, continuity reviewers, image runners |
| `p600` Scene/Image | production image prompts, scene requests, scene still generation, image handoff | scene/cut prompt workers, image prompt judges, image QA |
| `p700` Narration | narration review, TTS generation, duration fit, audio handoff | Narration Writer, duration reviewers, TTS workers |
| `p800` Video | motion prompts, clip generation, clip review/exclusions | video prompt reviewers, clip workers, clip reviewers |
| `p900` Render/QA | render inputs, final render, QA/runtime summary | QA reviewers, runtime summary reviewers |

### Director（監督）
- 入力: `research.md`
- 出力: `story.md`
- 参照: `docs/story-creation.md`
- Claude Code 互換 agent 定義: `.claude/agents/director.md`

### Visual Value Ideator
- 入力: `research.md` + `story.md`
- 出力: `visual_value.md`
- 目的: p300 visual planning の正本として、visual identity / scene visual value / anchor / reference strategy / asset bible candidates / regeneration risks / handoff を定義する
- 制約:
  - cut prompt、画像生成 request、asset 画像、動画 motion prompt は作らない
  - p400 / p600 / p700 が迷わない判断基準を `visual_value.md` に残す
  - silent visual payoff は p300 の一部機能であり、必要な run だけ `value_parts[]` に定義する
  - 文字ではなく、形 / 光 / 動き / 機構 / ショー性で伝える価値を優先する
- Claude Code 互換 agent 定義: `.claude/agents/visual-value-ideator.md`

### Scriptwriter
- 入力: `story.md` + `visual_value.md` + scene plan
- 出力: `script.md`
- 参照: `docs/script-creation.md`
- Kling 分岐: `video_generation.tool` が `kling_3_0` / `kling_3_0_omni` の場合、動画 prompt 設計は `docs/video-generation.md` の一般論ではなく `workflow/playbooks/video-generation/kling.md` を優先参照する

### Narration Writer（TTS原稿）
- 入力: `story.md` / `script.md` / `video_manifest.md`
- 出力: `video_manifest.md` の `audio.narration.text` と `audio.narration.tts_text`
- 原則:
  - `script.md` 側では `elevenlabs_prompt` を authoring source、`tts_text` を ElevenLabs v3 に送る final string として扱う
  - `tts_text` は ひらがな寄せを基本にしつつ、`[]` の audio tag を許可する
  - `voice_tags` は bracket なしの生タグで保持し、`tts_text` では順番通りに `[]` を付ける
  - どちらにも `TODO:` 等のメタ情報を書かない（空文字は可。未記入は生成時にエラー）
- 品質基準:
  - narration は cut の物語上の役割に従う
  - opening では、導入として安定した説明を優先し、scene/script に忠実であることを重視する
  - middle では、進展 / トラブル / 揺れを支える
  - ending では、解決 / 帰結 / 余韻を支える
  - 序盤では「無理に抽象的な内面や意味づけを足す」より、物語の入り口として自然であることを優先する
- Claude Code 互換 agent 定義: `.claude/agents/narration-writer.md`

### YouTube Thumbnail Prompt Writer
- 入力: ユーザーが指定した物語名（必須）
- 補助入力: `output/<topic>_<timestamp>/story.md` / `visual_value.md` / `video_manifest.md`（存在すれば参照）
- 出力: ユーザーへ返す `YouTube サムネイル用の構造化プロンプト`
- 目的: 物語名を大きく読ませる装飾文字中心のサムネ用 prompt を作り、背景・構図・可読性・画質条件まで一体で定義する
- 制約:
  - 画像生成 API 自体は呼ばない
  - 文字は既成フォントに寄せず、物語イメージから発想した独創的な造形にする
  - 背景は物語内容に合わせるが、文字可読性を最優先する
  - YouTube thumbnail 向けに `16:9`、`1280x720` 以上、高コントラスト、スマホ視認性を明記する
- Claude Code 互換 agent 定義: `.claude/agents/youtube-thumbnail-prompt-writer.md`

### Reviewer（Director兼務可）
- 入力: scene draft / script
- 出力: `accept | revise` + 理由

### p410 Scene Review Critics
- 入力: `story.md` / `visual_value.md` / `script.md` scene draft / stage readset
- 出力: 観点別 critic report。canonical artifact は編集しない
- 役割:
  - critic_1 `scene_count_coverage`: scene 数が `maximal_meaningful` まで展開され、独立 scene 化すべき主要 beat が埋もれていないかを見る
  - critic_2 `dramatic_structure + reveal_order`: 各 scene が独立した問い・価値変化・因果 turn を持つか、scene 追加/分割で reveal の早出し、欠落、順序破壊がないかを見る
  - critic_3 `duration_density`: scene 追加と cut 増厚のどちらが品質に効くかを、目標尺・重要度・cut 数で見る
  - critic_4 `visual_production`: 追加 scene が p500/p600/p800 へ渡せる visible evidence を持つかを見る
  - critic_5 `handoff_integrity`: scene 間の因果と handoff が途切れていないかを見る
  - aggregator は各 critic を統合し、次に追加できる scene と cut 増厚へ回す理由が説明できる場合だけ pass を返す

### p420 Cut Blueprint Review Critics
- 入力: `story.md` / `visual_value.md` / `script.md` cut blueprint draft / stage readset
- 出力: 観点別 critic report。canonical artifact は編集しない
- 役割:
  - critic_1 `cut_intent_isolation`: 1 cut = 1 intent が守られ、場所移動/reveal/感情反転/説明/反応を詰め込んでいないかを見る
  - critic_2 `beat_ladder_coverage`: cut_function 列が scene_spine を進め、重要 beat が段階分解されているかを見る
  - critic_3 `first_frame_motion_readiness`: first_frame_brief が p600 still の入力として完結し、motion_brief が p800 専用入力として分離されているかを見る
  - critic_4 `multimodal_contract_coverage`: target_beat / must_show / must_avoid / done_when が image / narration / motion へ渡せるかを見る
  - critic_5 `duration_density_and_handoff`: 重要度・尺・cut数・最終cutのhandoffが十分かを見る
  - aggregator は各 critic を統合し、`Cut Blueprint Gate` の全項目が説明できる場合だけ pass を返す

### Stage Evaluator
- 入力: `research.md` / `script.md` / `video_manifest.md` / `video.mp4`
- 出力: critic report / aggregator report + `state.txt` の `eval.<stage>.*`
- 役割:
  - authoring-after review slot では最大 5 round の evaluator-improvement loop として動く
  - 各 round では 5 critic agents が generator の出力を rubric/check 単位で独立採点する
  - 1 aggregator agent が critic finding を統合し、`passed|changes_requested` を返す
  - fail reason を次の修正 action に分解する
  - round 5 後も `changes_requested` の場合は human review / explicit override に回す
  - critic / aggregator は canonical artifact、`state.txt`、`p000_index.md` を直接編集しない
  - loop の起動、修正採否、次 round 判断は L1 ではなく担当 L2 P-Bucket Supervisor が行う

### QA / Compliance
- 入力: `research.md`, `story.md`, `script.md`, `video.mp4`
- 出力: QAスコア + pass/fail + 指摘
- 参照: `docs/orchestration-and-ops.md`

### Series Planner（scene-series）
- 入力: `story.md` / `script.md`
- 出力: `series_plan.md`
- Claude Code 互換 agent 定義: `.claude/agents/series-planner.md`

### Scene Evidence Researcher（scene-series）
- 入力: `research.md` + `series_plan.md`（question）
- 出力: `scenes/sceneXX/evidence.md`
- Claude Code 互換 agent 定義: `.claude/agents/scene-evidence-researcher.md`

### Scene Scriptwriter（scene-series）
- 入力: `scenes/sceneXX/evidence.md`
- 出力: `scenes/sceneXX/script.md`（30–60s）
- 品質ゲート: シーン必要性（ストーリー前進 / 矛盾・停滞なし / 登場人物の不可欠性 / テーマ整合）を自己点検して出力末尾に記録
<<<<<<< ours
<<<<<<< ours
<<<<<<< ours
- Claude Code 互換 agent 定義: `.claude/agents/scene-scriptwriter.md`
=======
=======
>>>>>>> theirs
=======
>>>>>>> theirs
- エージェント定義: `.claude/agents/scene-scriptwriter.md`
>>>>>>> theirs

## プロンプト構成

固定部と動的部に分離する。

- 固定部: 役割の目的 / 出力フォーマット / 品質基準
- 動的部: 入力成果物 / 制約 / 直近の指摘・修正理由

## バージョニング

- 形式: `role@vX.Y.Z`
- 変更履歴は `docs/prompt-changelog.md`（将来作成）に集約する

## Grounding / citation

- Research 出力は source を必須化
- Story/Script は research 参照を明示する
- `visual_value.md` は `research.md` / `story.md` と矛盾しない範囲で設計する

## 参照

- `docs/story-creation.md`
- `docs/script-creation.md`
- `docs/orchestration-and-ops.md`
- `workflow/playbooks/video-generation/kling.md`
