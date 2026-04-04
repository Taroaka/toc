# Multi-agent Immersive Narration Playbook (ToC)

目的: `/toc-immersive-ride` の `video_manifest.md` について、cuts（3〜5）に対応する
**ナレーション原稿（`audio.narration.text` / `audio.narration.tts_text`）**を衝突なく並列で作成する。

## 原則

- `audio.narration.text` は manifest 上の原稿でも、現行の elevenlabs 運用では **ひらがなだけ** を基本にする。
- `audio.narration.tts_text` は TTS に送る読み上げ専用原稿として扱う。
- `audio.narration.tts_text` は elevenlabs 用に、できるだけ **ひらがなだけ** で書く。`TODO:` などのメタ情報を書かない。
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
  - 先に `target_function` / `must_cover` / `must_avoid` / `done_when` を埋める
  - `cuts[].narration_text` に物語として自然な **ひらがな原稿**を書く
  - `cuts[].tts_text` に elevenlabs へ送る **ひらがな原稿**を書く
  - 1カット=1ナレーション
  - main=5–15秒、sub=3–15秒を目安に短く

## Phase 2: Merge to manifest（直列）

single-writer が scratch を manifest へ統合:

```bash
python scripts/ai/merge-immersive-narration.py \
  --run-dir "output/<topic>_<timestamp>_immersive"
```

## Phase 2.5: Narration review（直列）

統合後に subagent review を実行し、`audio.narration.review` を source manifest に書き戻す:

```bash
python scripts/review-narration-text-quality.py \
  --manifest "output/<topic>_<timestamp>_immersive/video_manifest.md"
```

- finding が出た scene/cut は `agent_review_ok: false` と reason key を持つ
- contract 未定義や must cover 未達も finding になる
- fix は source manifest 側へ反映し、再 review してから次へ進む
- `human_review_ok: true` は例外許容の記録であり、subagent finding 自体は消さない

## Phase 3: Next（ユーザーが起動）

原稿が埋まったら、音声→尺同期→映像生成へ進む:

```bash
scripts/toc-immersive-ride-generate.sh --run-dir "output/<topic>_<timestamp>_immersive"
```
