# Multi-agent Immersive Narration Playbook (ToC)

目的: `/toc-immersive-ride` の `video_manifest.md` について、cuts（3〜5）に対応する
**ナレーション原稿（`audio.narration.text` / `audio.narration.tts_text`）**を衝突なく並列で作成する。

## 原則

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
- 共有ファイル（`video_manifest.md`）は **同時編集しない**（single-writer で統合）。
- 並列化は「scene別 scratch」→「1人がマージ」で実現する。

## ファイル構成（run dir）

`output/<topic>_<timestamp>_immersive/`
- `video_manifest.md`（正本 / single-writer が更新）
- `state.txt`（必要なら single-writer が更新）
- `scratch/narration/sceneXX.yaml`（scene担当が編集 / scene単位で競合しない）

## Phase 0: Prepare scratch（直列）

single-writer が scratch 雛形を作る:

```bash
python scripts/ai/toc-immersive-narration-multiagent.py \
  --run-dir "output/<topic>_<timestamp>_immersive" \
  --min-cuts 3
```

## Phase 1: Per-scene narration drafting（並列）

scene担当者は、自分の scene の scratch だけ編集して原稿を入れる:

- 例: `scratch/narration/scene02.yaml`
  - 先に `story_role.narrative_position` / `cut_function` / `voice_function` / `visual_distance.distance_policy` を埋める
  - `narration_should_add` には、映像だけでは言えない内面・因果・時間・余韻を置く
  - 誤読しそうな語は `tts_readiness.pronunciation_targets` に置く
  - `cuts[].narration_text` に物語として自然な原稿を書く
  - `cuts[].spoken_context` / `cuts[].voice_tags` / `cuts[].spoken_body` / `cuts[].stability_profile` を決める
  - `cuts[].tts_text` に ElevenLabs v3 へ送る final string を置く
  - 1カット=1ナレーション
  - main=5–15秒、sub=3–15秒を目安に短く

## Phase 2: Merge to manifest（直列）

single-writer が scratch を manifest へ統合:

```bash
python scripts/ai/merge-immersive-narration.py \
  --run-dir "output/<topic>_<timestamp>_immersive"
```

## Phase 2.5: Narration review（直列）

統合後に p720 L3 review を実行し、`audio.narration.review` を source manifest に書き戻し、5 critic + 1 aggregator artifact を残す:

```bash
python scripts/run-p720-narration-l3.py \
  --run-dir "output/<topic>_<timestamp>_immersive" \
  --fail-on-findings
```

- finding が出た scene/cut は `agent_review_ok: false` と reason key を持つ
- L3 artifact は `logs/eval/narration/round_01/critic_*.md` と `logs/eval/narration/round_01/aggregated_review.md` に残る
- 設計目標の critic split は `story_role` / `visual_distance` / `tts_delivery` / `arc_and_pacing` / `spoken_japanese`
- 現行 runner が generic `critic_*.md` を出す場合でも、aggregator は上記5観点を report 内で明示する
- 発音候補は設計目標として `logs/eval/narration/round_01/pronunciation_candidates.tsv` に出せる。未実装時は aggregator report または human handoff に候補を明記する
- cut 単体では見つからない声の流れは、設計目標として `narration_arc_review` にまとめる
- contract 未定義や must cover 未達も finding になる
- fix は source manifest 側へ反映し、再 review してから次へ進む
- `human_review_ok: true` は例外許容の記録であり、subagent finding 自体は消さない

## Phase 3: Next（ユーザーが起動）

原稿が埋まったら、音声→尺同期→映像生成へ進む:

```bash
scripts/toc-immersive-ride-generate.sh --run-dir "output/<topic>_<timestamp>_immersive"
```
