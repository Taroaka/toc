# Multi-agent Immersive Narration Playbook (ToC)

目的: `/toc-immersive-ride` の全編音声を先に設計し、通し原稿を narration span と cut anchor へ割り当て、
`script.md` を言語正本として衝突なく統合する。

## 原則

- 設計keyの採否は `toc/narration_prompt_projection_registry.py` を正本にし、詳細は
  `docs/implementation/narration-prompting.md` に従う。新keyはrunnerへ直接足さず、registryへ
  `authoring_relevance` / `spoken_projection` / transform / review観点を登録する。
- authoring promptとp720 semantic reviewは同じprojection contractを使う。semantic criticだけが音声・映像距離の
  判定用 `review_only` visual contextを追加で読む。背景情報を自動的に読み上げず、`must_not_surface`の内部ID、
  reveal制約、visible fact、provider promptを本文へ流さない。
- `audio.narration.tts_text` は ElevenLabs v3 に送る final string として扱う。
- `tts_text` は ひらがな寄せを基本にしつつ、`[]` の audio tag を許可する。`TODO:` などのメタ情報は書かない。
- 未記入の narration は `text` / `tts_text` に placeholder を置かず、空文字 + `authoring_status: missing` で表す。
- `audio.narration.contract.schema_version: narration_contract_v2` を前提に、`story_role.narrative_position` / `story_role.cut_function` / `story_role.voice_function` と `visual_distance.distance_policy` を先に決める。
- 下書きでは `spoken_context` / `voice_tags` / `spoken_body` / `stability_profile` を先に決め、必要ならそこから `tts_text` を組み立てる。
- `narration` と `visual_beat` の距離は固定ではない。
  - 序盤 / 中盤は原則 `stay_close`
  - 終盤は `contextual`
  - 代償や余韻を残す cut だけ `meaning_first` を許容する
- 目標は「常に差を作る」ことではなく、必要な cut にだけ **映像のあとに意味が残る一文** を置くこと
- `1 cut = 1 narration` は必須ではない。spanは複数cutをまたいでよい。
- 共有ファイル（`script.md`）は **同時編集しない**（single-writer で統合）。
- frontend の `human_locked` 文面は上書きせず、矛盾は `changes_requested` にする。
- 並列化は「scene別 scratch」→「1人がマージ」で実現する。

## ファイル構成（run dir）

`output/<topic>_<timestamp>_immersive/`
- `script.md`（ナレーション言語正本 / single-writer が更新）
- `video_manifest.md`（実行用派生物 / script承認後に一方向同期）
- `state.txt`（必要なら single-writer が更新）
- `scratch/narration/authoring_prompt.md`（全編設計の正規authoring prompt）
- `scratch/narration/audio_story.yaml`（全編plan / continuous draft / spans。single-writerが統合）
- `scratch/narration/sceneXX.yaml`（scene担当が編集 / scene単位で競合しない）

## Phase 0: Prepare scratch（直列）

single-writer が scratch 雛形を作る:

```bash
python scripts/ai/toc-immersive-narration-multiagent.py \
  --run-dir "output/<topic>_<timestamp>_immersive" \
  --min-cuts 3
```

runner はmanifestの実cut IDからscene scratchを作り、同時に`audio_story.yaml`と
`authoring_prompt.md`をmaterializeする。既存の`audio_story.yaml`は上書きしない。
`--scene-ids` / `--start-scene-id`は並列scene scratchの担当範囲だけを絞り、全編plan・prompt・locked inventoryは常に全story sceneを対象にする。
対象は後段と同じactive inventoryに限定し、deleted/reference/character-asset nodeは含めない。dotted numeric IDは保持し、
`scene10_cut1.1`のscratch selectorを整数化しない（dotted sceneのscratch filenameだけは`scene10_1.yaml`のようにpath-safe化する）。
frontendで`human_locked` / `reviewed` / `silent`になったcutがある場合は、再実行時に
selector・確定`text`・確定`tts_text`を`locked_cut_inputs`とscene scratchのread-only seedへ同期する。

## Phase 1: Full-run audio treatment（直列）

single-writer は`authoring_prompt.md`を読み、`audio_story.yaml`に`audio_story_plan`を作る。
audience promise、narrator bible、open loop/payoff、
scene attention arc、因果handoff、silence budgetを固定する。続けてcut境界なしの
`continuous_full_draft` を作る。全編reviewとcanonical projection照合後に
`authoring_provenance: audio_story_director` / `authoring_status: authored`へ進める。

## Phase 2: Per-scene/span drafting（並列）

scene担当者は、自分の scene の scratch だけ編集して原稿を入れる:

- 例: `scratch/narration/scene02.yaml`
  - 先に `story_role.narrative_position` / `cut_function` / `voice_function` / `visual_distance.distance_policy` を埋める
  - `narration_should_add` には、映像だけでは言えない内面・因果・時間・余韻を置く
  - 誤読しそうな語は `tts_readiness.pronunciation_targets` に置く
  - 通し原稿の担当範囲を磨き、`narration_spans[]` と source cut anchors を提案する
  - `cuts[].spoken_context` / `cuts[].voice_tags` / `cuts[].spoken_body` / `cuts[].stability_profile` を決める
  - `cuts[].tts_text` に ElevenLabs v3 へ送る final string を置く
  - 同じ声の流れを保つspanへ同じ`tts_generation_group_id`を付ける。1つのvoiced cutを複数groupへ所属させない
  - human_locked spanは変更しない
  - main=5–15秒、sub=3–15秒を目安にしつつ、短いcutごとに演技を分断しない

## Phase 3: Merge to script and sync（直列）

single-writer が scratch を `script.md` の通し原稿とspan mapへ統合し、全編接続を再確認する。
structured `script.md` があるrevision-aware runでは、merge commandがhuman_lockedを保護しながらscriptへ統合し、
run artifact lockを保持したままmanifestへ一方向同期する。revision-aware manifestしかなくstructured scriptが無い場合は、直接mergeせず停止する:

```bash
python scripts/ai/merge-immersive-narration.py \
  --run-dir "output/<topic>_<timestamp>_immersive"
```

- 各voiced cutは原則ちょうど1つのvoiced spanに属する
- spanの`text` / `tts_text`は`source_cut_ids`順のnon-empty cut原稿を改行連結した値にする
- `continuous_full_draft`はvoiced spanの`text`をspan順に改行連結した値にする
- 既存`audio_story.yaml`がこのcanonical projectionとずれる場合、mergeは暗黙修正せず失敗する
- frontend確定cutはscene scratchの内容や`--force`より優先し、global plan/spanを確定文へ合わせる
- merge後のscript→manifest→state同期は一つのtransactionで、途中失敗時は3成果物を開始前のbyte列へ戻す
- 旧runでglobal scratchがまだ無い場合だけ、初回mergeはcut原稿からcanonical plan/span/draftを生成する。このfallbackは`authoring_provenance: derived_legacy_cut_projection` / `authoring_status: changes_requested`となり、Audio Story Directorのreview完了までp720を通さない

## Phase 4: Narration review（直列）

統合後のp720は二層で実行する。先にdeterministic arc/cut reviewを実行し、そのsnapshotが通った後で
5つの独立app-server semantic criticを実行する。

```bash
python scripts/run-p720-narration-l3.py \
  --run-dir "output/<topic>_<timestamp>_immersive" \
  --fail-on-findings

python scripts/run-p720-narration-semantic.py \
  --run-dir "output/<topic>_<timestamp>_immersive" \
  --fail-on-findings
```

- `run-p720-narration-l3.py`は再現可能なruleでcontract、TTS readiness、局所visual重複、plan/span/cut/open-loop整合を検査する
- finding が出た scene/cut は `agent_review_ok: false` と reason key を持つ
- L3 artifact は `logs/eval/narration/round_01/critic_*.md` と `logs/eval/narration/round_01/aggregated_review.md` に残る
- この`critic_*.md`はdeterministic findingを5観点へ分類した互換artifactであり、5つの独立LLM verdictではない
- `run-p720-narration-semantic.py`は同じtext hashとexact semantic input hashへ束縛したfull-run packを別threadで評価する
  - `retention_hook`: 冒頭の約束、open loop、注意の更新
  - `narrator_voice_persona`: narrator bible、知識境界、声の一貫性
  - `causal_information_rhythm`: 因果・reveal順、情報密度、handoff
  - `audio_visual_distance`: 映像キャプション化、先取り、沈黙、追加価値
  - `payoff_ending`: audience promiseの回収、reaction、aftertaste
- semantic resultは`narration_workflow.semantic_critic_review`へ保存し、report/jsonを
  `logs/eval/narration/semantic_critics/`へ残す
- exact input hashはvisual beat、contract、画像/動画prompt、duration/offsetも含む。固定5 criticの欠落・重複、
  response/aggregate/report/json不一致はpassにしない
- critic threadはisolated cwd、sensitive env scrub、tool無効config、structured output、instruction/data分離を使い、
  tool/command/file eventを観測したturnはfail closedにする
- app-server無効、実行失敗、欠落/malformed JSON、critic/hash不一致はblockingとしてfail closedにする。
  review中にmanifest hashが変わった結果は保存せず、current snapshotで再実行する
- 発音候補は設計目標として `logs/eval/narration/round_01/pronunciation_candidates.tsv` に出せる。未実装時は aggregator report または human handoff に候補を明記する
- cut 単体では見つからない声の流れはrun-level `narration_workflow.arc_review`にまとめ、
  deterministic `status: passed`とcurrent `narration_text_set_hash`を記録する
- p750にはcurrent `arc_review.status: passed`とcurrent `semantic_critic_review.status: passed`の両方を必須にする
- contract 未定義や must cover 未達も finding になる
- fix は `script.md` 側へ反映し、一方向同期と再reviewを行う
- `human_review_ok: true` は例外許容の記録であり、subagent finding 自体は消さない
- frontendの`POST /api/image-gen/narration-review/run`も上記二層を同じ順で実行する。p720 と p730 は
  下書き保存・文面確定・TTS候補試聴によって往復してよい。生成成功は承認ではない。

## Phase 5: Frontend audio approval（ユーザーが操作）

revision-aware runでは、frontendで次を別操作として行う。

1. current revisionを使って下書き保存または`human_locked`確定
2. current revision/TTS hashからimmutable candidateを生成
3. 試聴後、cutごとにcurrent candidateまたはintentional silenceを承認
4. deterministic arc/semantic criticのcurrent passとp740 duration fitを確認
5. current `audioSetHash`と全cut・canonical順のtimelineを送ってp750全編承認

全編試聴は全音声のfetch/decodeを先に完了し、単一AudioContext clockへ全cutをscheduleする。通信時間をcut間へ混入させず、
timeline末尾のcompletion markerまで到達した場合だけlisten evidenceを発行する。1 cut/render unitが60秒を超える場合は分割する。

生成時は同一`tts_generation_group_id`の前後cut文面をElevenLabs contextへ渡し、`tts_continuity_hash`をsnapshotへ固定する。
隣接memberのTTS文面が変わったcandidateも`stale`として残るが採用されない。p750はaudio set hashとtimeline hashを固定し、
その後の文面、TTS、delivery、candidate、audio file、duration/offset変更でstaleになる。

## Phase 6: Next（ユーザーが起動）

p750完了後、映像生成へ進む:

```bash
scripts/toc-immersive-ride-generate.sh --run-dir "output/<topic>_<timestamp>_immersive"
```

current p750が無いrevision-aware runでは、このCLIはaudioを自動生成せず
`runtime.stage=narration_frontend_handoff`で停止する。frontend承認後に同じcommandを再実行する。
`generate-assets-from-manifest.py`の直接audio passもrevision-aware manifestでは拒否し、legacy TTS書込へfallbackしない。
