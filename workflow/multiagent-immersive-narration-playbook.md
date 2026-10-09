# Immersive Narration Playbook (ToC)

目的: `/toc-immersive-ride` の全編音声を先に設計し、通し原稿を narration span と cut anchor へ
割り当て、`script.md` を言語正本として統合する。p720 の production worker は retired。
p700 は authoring、TTS、実測 duration、任意の user listening/selection を扱う。

## 原則

執筆前に `docs/implementation/narration-prompting.md` の標準の語り口・音声タグ・単語の修正を読む。
ですます調・落ち着いた語り・平易な用語を基本とし、TTS本文に語り方タグと読みを入れる。
runの `narration_style.json` に承認済みの指示がある場合はそれを引き継ぐ。

- `toc/narration_prompt_projection_registry.py` の `authoring_relevance` と
  `spoken_projection` を使い、design key を spoken text へ一方向に投影する。
- `tts_text` は ElevenLabs v4 の final string。TODO や制作 metadata を入れない。
- 未記入は `text: ""`、`tts_text: ""`、`authoring_status: missing` で表す。
- `story_role`、`visual_distance`、`tts_readiness`、silence contract を authoring 時に決める。
- `1 cut = 1 narration` は必須ではない。span は複数 cut をまたげる。
- `script.md` は single writer が更新し、scene scratch は worker ごとに分ける。
- `human_locked` text は user が明示した current source として保護する。
- candidate listening、candidate selection、text editing は optional user actions。選択後に
  revision/hash/provenance を普通に検証する。

## Run files

```text
output/<topic>_<timestamp>_immersive/
  script.md
  video_manifest.md
  state.txt
  scratch/narration/authoring_prompt.md
  scratch/narration/audio_story.yaml
  scratch/narration/sceneXX.yaml
  logs/validation/
```

## Phase 0: Prepare scratch

```bash
python scripts/ai/toc-immersive-narration-multiagent.py \
  --run-dir "output/<topic>_<timestamp>_immersive"
```

runner は manifest の active cut IDs から scene scratch と full-run audio plan を作る。
deleted/reference-only nodes は除外する。dotted numeric selector は path-safe filename に
変換しても canonical selector 自体は変更しない。既存の user locked text は read-only seed として保つ。

## Phase 1: Full-run authoring

single writer が authoring prompt を読み、`audio_story_plan` と continuous full draft を作る。

1. audience promise、narrator bible、open loop/payoff、scene attention arc、causal handoff、silence budget
2. cut 境界なしの `continuous_full_draft`
3. `narration_spans[]` と source cut anchors
4. readable `text`、TTS 用 `tts_text`、pronunciation targets

原稿は [音声だけで理解できる説明の具体性](../docs/implementation/narration-prompting.md#音声だけで理解できる説明の具体性) に従う。
映像との重複回避や尺の都合で、理解に必要な場所・対象・期限・因果を削らない。
執筆者は通し原稿を音声だけのつもりで読み直し、曖昧な指示語や行為の省略を補ってからTTSへ渡す。

全編の canonical order、source event boundary、visible overlap、TTS normalization は ordinary
structural checks で確認する。

## Phase 2: Per-scene drafting

scene worker は専用 scratch だけを編集する。

- `story_role.narrative_position`、`cut_function`、`voice_function`
- `visual_distance.distance_policy` と `narration_should_add`
- pronunciation targets、pause、prosody、`tts_generation_group_id`
- continuous full draft の担当範囲と `narration_spans[]`
- visual-only cut の intentional silence reason/duration

worker は source cut IDs、text、TTS text、user locked marker を変更するとき source contract を
参照し、canonical story facts/reveal order を暗黙に変更しない。

## Phase 3: Merge and sync

```bash
python scripts/ai/merge-immersive-narration.py \
  --run-dir "output/<topic>_<timestamp>_immersive"
```

single writer は scene scratch を `script.md` へ merge し、`video_manifest.md` へ一方向同期する。

- voiced cut は通常一つ以上の voiced span に anchor する
- span text/tts_text は source cut order の projection
- continuous full draft は span order の projection
- locked text、source IDs、selector、revision が一致しない merge は停止する
- script、manifest、state の更新を一つの lock/transaction で行う
- 変更後は narration text/hash、TTS settings、pronunciation alias を再検証する

## Phase 4: TTS and duration

p730 で current narration revision から TTS candidate を生成し、response item、request hash、
voice/model/settings、pronunciation dictionary、audio path、content hash を記録する。生成中に
revision が変わった音声は stale candidate として保存し、current output には昇格しない。

p740 で ffprobe などを使って spoken audio と intentional silence を測定し、audio timeline を
作る。video timeline は video clip/render-unit duration として別に測る。対象 timeline、stream、
duration、decode、provenance が揃うまで video request を作らない。

p750 は audio QA/data handoff と optional user listening/selection を置く slot である。ユーザーが
candidate を選ぶ場合だけ `human_choice.*` と selected revision を保存する。user choice がない
場合も、measured audio と structural checks が通れば p750 は完了できる。

## Phase 5: Video handoff

```bash
scripts/toc-immersive-ride-generate.sh \
  --run-dir "output/<topic>_<timestamp>_immersive"
```

video generator は current manifest payload、audio timeline、first/last frame、ordered references、
prompt/source hashes を使う。direct audio generation が current script/TTS revisionを迂回する
経路は使わない。p720 review artifact、critic、aggregate、score、mandatory approval の存在は
要求しない。

## State and resume

state は append-only。p710/p730/p740/p750 の stage/slot status、narration revision、audio hash、
timeline、request provenance を記録する。resume は stale downstream item だけを再生成し、
valid audio と user choice は完全な binding が一致する限り保持する。
