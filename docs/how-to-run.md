# How to Run (MVP)

本書は `todo.txt` の 15) Documentation に対応する。

## 前提
- 起点は Claude Code の slash command（例: `/toc-run`, `/toc-scene-series`, `/toc-immersive-ride`）
- 成果物は `output/<topic>_<timestamp>/` に生成される
- 成果物（`research.md` / `story.md` / `script.md` / `video_manifest.md` 等）の本文は **日本語**で記述する（ユーザーがそのまま修正できるように）
  - 例外: ツール名 / ファイルパス / コード / 固有名詞はそのまま（必要なら英語併記はOK）
- state は `output/<topic>_<timestamp>/state.txt`（追記型）
- 方針: **創造→選択**
  - Research は多様性（登場人物/世界観/解釈）を厚めに集め、Story/Script でスコアが高い案を選択する
  - 矛盾する複数ソースの要素を同一シーン/設定として混成（ハイブリッド）する必要が出た場合は、確定前にユーザー承認を取る（運用）

## セットアップ（Docker）

1) `.env.example` を `.env` にコピーし、APIキー等を設定する  
2) 起動:

```bash
docker-compose up --build
```

## セットアップ（uv / local）

uv で依存を揃える場合（.venv を作って同期）:

```bash
python -m pip install -U uv
scripts/uv-sync.sh
```

## 実行（想定）

Claude Code で以下を実行:

```
/toc-run "桃太郎" --dry-run
```

story review を後回しにして script draft まで一気に進める run:

```text
/toc-run "かぐや姫" --dry-run --review-policy drafts
```

YouTube サムネイル用の prompt だけ作る場合:

```text
/toc-youtube-thumbnail "桃太郎"
```

既存 run dir を参照して、作品内容に寄せたサムネ prompt を作る場合:

```text
/toc-youtube-thumbnail "浦島太郎" --run-dir output/浦島太郎_<timestamp>
```

sceneごとにQ&A動画を複数本作る場合:

```
/toc-scene-series "桃太郎" --min-seconds 30 --max-seconds 60
```

シーンエージェント（multi-agent）で scene-series の下準備を行う場合:

```bash
python scripts/ai/toc-scene-series-multiagent.py "桃太郎" --min-seconds 30 --max-seconds 60
python scripts/toc-scene-series.py "桃太郎" --run-dir output/桃太郎_<timestamp>
```

没入型（実写シネマティック体験）の単発動画:

```text
/toc-immersive-ride --topic "桃太郎"
```

API をまだ使わず、story/script/manifest draft まで進めたい場合:

```text
/toc-immersive-ride --topic "かぐや姫" --stage script --experience cinematic_story --review-policy drafts
```

## 期待される出力（/toc-run）

```
output/<topic>_<timestamp>/
  p000_index.md
  state.txt
  research.md
  story.md
  script.md
  video_manifest.md
  video.mp4          (プレースホルダでも可)
  run_report.md
  logs/
```

## 期待される出力（/toc-scene-series）

```
output/<topic>_<timestamp>/
  p000_index.md
  state.txt
  research.md
  story.md
  series_plan.md
  scenes/
    scene01/
      evidence.md
      script.md
      video_manifest.md
      assets/
      video.mp4
    scene02/
      ...
```

## 生成（画像/動画/TTS）について

- 画像: Google Nano Banana Pro（Gemini Image / `gemini-3-pro-image-preview`）
- 画像（代替）: SeaDream / Seedream 4.5（`tool: "seadream"` + `SEADREAM_*`）
- 動画: Kling 3.0（default。`video_generation.tool: "kling_3_0"` + `KLING_ACCESS_KEY`/`KLING_SECRET_KEY`）
- 動画（Omni）: Kling 3.0 Omni（`video_generation.tool: "kling_3_0_omni"` + `KLING_OMNI_*`）
- 動画（代替）: Seedance（BytePlus ModelArk。`video_generation.tool: "seedance"` + `ARK_API_KEY`）
- ※ Google Veo はこのリポジトリでは安全のため無効化（Veo系の tool 名は Kling にルーティング）
- TTS: ElevenLabs
- 当面は `video_manifest.md` を入力に素材生成→結合でフローを検証する
- 具体は `docs/implementation/video-integration.md` を参照
- 画像生成の review 正本は `video_manifest.md` 自体
- `review-image-prompt-story-consistency.py` は manifest を直接監査し、結果を `image_generation.review` へ書き戻してから画像生成へ進む
  - hard gate は missing contract / missing ids / required prompt block 欠落 / reveal 破り / self-contained 違反のような構造的問題に寄せる
  - `must_avoid` の素朴な文字列一致、`target_focus` の語一致、`production_readiness` の弱さは warning として残してよい
- reusable asset が多い run では、cut 画像生成の前に `asset_plan.md` を作って review / approve してから asset を生成する
- image の rerun で比較案が欲しい場合だけ、`generate-assets-from-manifest.py --force --test-image-variants N` を使って `assets/test/` に exploratory variant を出す
- provider 実行前に request file を materialize できる
  - asset stage: `asset_generation_requests.md`
  - cut image stage: `image_generation_requests.md`
  - video stage: `video_generation_requests.md`
- `p000_index.md` は run 直下の人間向け入口
  - current stage
  - next required human review
  - stage table
  - current run inventory
  をまとめる
  - 手動再生成: `python scripts/build-run-index.py --run-dir output/<topic>_<timestamp>`
- `100` 番台ごとに大工程を割り当てる
  - `p100`: research
  - `p200`: story
  - `p300`: visual planning
  - `p400`: script / narration text / human changes
  - `p500`: asset
  - `p600`: image
  - `p700`: video
  - `p800`: audio generation
  - `p900`: render / QA / runtime
- これらの slot 意味は固定契約で、story ごとに変えない
- 細番号も固定 slot contract の一部として扱う
  - `p110`, `p120`, `p130`
  - `p210`, `p220`, `p230`
  - `p310`, `p320`, `p330`
  - `p410`, `p420`, `p430`, `p440`
  - `p510`, `p520`, `p530`, `p540`, `p550`, `p560`, `p570`, `p580`
  - `p610`, `p620`, `p630`, `p640`, `p650`, `p660`, `p670`
  - `p710`, `p720`, `p730`, `p740`, `p750`
  - `p810`, `p820`, `p830`
  - `p910`, `p920`, `p930`
- story ごとの差分は `slot.pXXX.status` / `slot.pXXX.requirement` / `slot.pXXX.skip_reason` / `slot.pXXX.note` で表す
- `skip` は例外ではなく正規状態で、ユーザー指示に応じて run ごとに記録してよい
- `p000_index.md` の stage table / slot table を、その run の進捗正本とする
- slot 状態を手で残したい場合は次を使う

```bash
python scripts/toc-state.py set-slot \
  --run-dir output/<topic>_<timestamp> \
  --slot p540 \
  --status skipped \
  --requirement optional \
  --skip-reason "asset stage not needed for this run"
```

- fixed `p-slot` contract を更新したら `python scripts/validate-slot-contract.py` を実行する
- `python scripts/generate-assets-from-manifest.py --manifest ... --materialize-request-files-only` で request file だけ更新できる
- request file の手修正は正本ではなく、次回 materialize で再構成される
- 修正理由を残したい場合は `script.md.human_change_requests[]` を正本にし、materialized request file の `source_requests` を review に使う
- 同時に `generation_exclusion_report.md` も更新され、`cut_status: deleted` の cut が request / generation / concat から外れることを確認できる
- 人間レビューが gate になっている stage では、作業完了時に「次はユーザーの review が必要」という短い促しを必ず返す
- `review-narration-text-quality.py` は manifest を直接監査し、結果を `audio.narration.review` へ書き戻してから音声生成へ進む
- ナレーション文面の human review 正本は `script.md`
  - `script.md` の `narration` / `tts_text` / `human_review.approved_*` を更新してから manifest へ同期する
  - 同期コマンド:

```bash
python scripts/sync-narration-from-script.py \
  --script output/<topic>_<timestamp>/script.md \
  --manifest output/<topic>_<timestamp>/video_manifest.md
```

- `review-research-stage.py` / `review-script-stage.py` / `review-manifest-stage.py` / `review-video-stage.py` は各 stage の evaluator subagent review を担い、report と `state.txt` の `eval.*` summary を更新する
  - research は `research.md.evaluation_contract`
  - script は `script.md.evaluation_contract`
  - scene/cut は `video_manifest.md.scenes[].cuts[].scene_contract`
  - video は `video_manifest.md.quality_check.review_contract`
- narration の作成前に `audio.narration.contract` を置き、cut ごとの done 条件を明示してから原稿を書く
- review では、不足 `character_ids` の自動補完、prompt が環境寄りに流れすぎていないか、story 上の関係性/ブロッキングが抜けていないかを点検する
- `image_generation.review` は `agent_review_ok` / `agent_review_reason_keys` / `rubric_scores` / `overall_score` / `human_review_ok` / `human_review_reason` を持つ
  - `image_generation.contract` は `target_focus` / `must_include` / `must_avoid` / `done_when` を持てる
  - criterion score は `rubric_scores`、加重合計は `overall_score` に入る
  - 現行表記として `agent_review_reason_codes` を使っていてもよいが、意味は `agent_review_reason_keys` と同じに保つ
  - review 実行後に subagent が `agent_review_ok` を更新する
  - `human_review_ok` は初期値 `false`
  - false の cut には reason key を 1 つ以上残す
  - canonical reason key は `image_contract_missing` / `image_contract_must_include_unmet` / `image_contract_must_avoid_violated` / `image_contract_target_focus_unmet` / `missing_required_prompt_block` / `prompt_not_self_contained` / `non_japanese_prompt_term` / `prompt_mentions_character_but_character_ids_empty` / `source_anchor_missing_from_prompt` / `missing_character_id` / `missing_object_id` / `prompt_only_local_mismatch` / `prompt_missing_expected_character_anchor` / `prompt_missing_expected_object_anchor` / `prompt_subject_drift` / `blocking_drift` / `image_prompt_story_alignment_weak` / `image_prompt_subject_specificity_weak` / `image_prompt_continuity_weak` / `image_prompt_production_readiness_weak`
  - required block `[全体 / 不変条件]` / `[登場人物]` / `[小道具 / 舞台装置]` / `[シーン]` / `[連続性]` / `[禁止]` のいずれかが欠けていれば、subagent は `agent_review_ok: false` にする
  - この場合の canonical reason key は `missing_required_prompt_block`
  - prompt が `scene03_cut01` のような他 cut 参照や `前カット` / `次カット` / `前のprompt` のような参照依存表現を含む場合、subagent は `agent_review_ok: false` にする
  - この場合の canonical reason key は `prompt_not_self_contained`
  - prompt に `rideable` のような英語 shorthand が混ざる場合も false にする
  - この場合の canonical reason key は `non_japanese_prompt_term`
  - prompt に人物が明示されているのに `image_generation.character_ids` が空なら false にする
  - この場合の canonical reason key は `prompt_mentions_character_but_character_ids_empty`
  - false reason に対応する修正を manifest に反映し、修正後に再 review して finding が消えれば、subagent はその cut を `agent_review_ok: true` に戻す
  - `human_review_ok: true` は finding を理解して例外許容した記録であり、subagent finding を消す意味ではない
  - `human_review_ok: true` のときは `human_review_reason` を残す
  - **両方 `false` の cut が残っていると画像生成は止まる**
- `audio.narration.review` は `agent_review_ok` / `agent_review_reason_keys` / `agent_review_reason_messages` / `human_review_ok` / `human_review_reason` を持つ
  - `audio.narration.contract` は `target_function` / `must_cover` / `must_avoid` / `done_when` を持てる
  - human review は先に `script.md` 側で行い、manifest 側は同期結果を gate する
  - criterion score は `rubric_scores`、加重合計は `overall_score` に入る
  - review 実行後に subagent が `agent_review_ok` を更新する
  - `human_review_ok` は初期値 `false`
  - false の cut/scene には reason key を 1 つ以上残す
  - canonical reason key は `narration_contract_missing` / `narration_contract_must_cover_unmet` / `narration_contract_must_avoid_violated` / `narration_contract_target_function_unmet` / `narration_empty` / `narration_tts_text_missing` / `narration_text_not_hiragana_only` / `tts_text_not_hiragana_only` / `narration_contains_meta_marker` / `tts_unfriendly_literal` / `unsupported_audio_tag_for_v2` / `needs_text_normalization` / `sentence_too_long_for_tts` / `missing_pause_punctuation` / `visual_direction_leaked_into_narration` / `narration_story_role_mismatch` / `narration_too_visual_redundant` / `narration_pacing_mismatch` / `narration_spoken_japanese_weak`
  - false reason に対応する修正を manifest に反映し、修正後に再 review して finding が消えれば、subagent はその node を `agent_review_ok: true` に戻す
  - `human_review_ok: true` は finding を理解して例外許容した記録であり、subagent finding を消す意味ではない
  - **両方 `false` の node が残っていると音声生成は止まる**
- 画像生成の既定サイズは `1K`（必要な scene だけ `image_generation.image_size` で上書き）
- story still の既定生成対象は `still_image_plan.mode: generate_still` のみ
  - `reuse_anchor` / `no_dedicated_still` は既定では生成しない
  - 例外的に広げるときだけ `--image-plan-modes generate_still,reuse_anchor` のように指定する
- `image_generation_requests.md` には review 用に image prompt を持つ全 scene/cut を出す
  - `still_mode` と `generation_status` を見れば、新規生成 / 再利用 / bridge の扱いが分かる
  - `generation_status` は `missing|created|recreate`
  - `cut_status: deleted` の cut は request 本文には出さず、`generation_exclusion_report.md` に送る
  - `references` は explicit path だけでなく、`character_ids` / `object_ids` / `location_ids` から解決された asset も含め、人レビュー時に参照元が見えるようにする
  - 画像生成は依存のない cut から並列化され、`--image-max-concurrency` で同時実行数を制御できる（上限 10）
  - `recreate` を実際に回すときは `--force` を使う
  - `recreate + --force` では既存 canonical 画像を `assets/test/` に退避してから上書きする
  - `--force --test-image-variants N` を併用すれば exploratory variant を複数出せる
- scene 3 以降など大きい範囲をまとめて見直すときは、scene 単位で request authoring subagent を並列起動して scratch rewrite を作り、メインエージェントが `image_generation_requests.md` へ統合する
  - 各担当は `script.md`、`video_manifest.md`、現在の request draft、`docs/implementation/image-prompting.md` を必ず読む
  - motion や first/last frame の判断が絡む scene では `docs/video-generation.md` も必ず読む
  - 担当 scene の `visual_beat` を semantic source にして、stateless な request 文へ書き直す
  - この scene 分割は毎回の image generation run で再現できるよう、順番・担当範囲・統合手順を固定する
  - semantic source は `script.md`、implementation source は `video_manifest.md`
  - request 本文の具体化はコードで自動変換せず、自然言語エージェントと人レビューで決める
- `scripts/build-clip-lists.py` は `*_generation_exclusions.md` も出力する
  - `cut_status: deleted` の cut は `video_clips.txt` / `video_narration_list.txt` から自動で除外される
  - 最終 render はこの concat list を正本として使う
- `--apply-asset-guides --asset-guides-character-refs scene` で人物 still を回す場合、既存の `assets/characters/*_refstrip.png` は reference に自動で追加される

例（`momotaro` のマニフェストから素材生成→結合）:

```bash
python scripts/review-image-prompt-story-consistency.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --fix-character-ids

python scripts/review-research-stage.py \
  --run-dir output/momotaro_20260110_1700 \
  --profile standard

python scripts/review-script-stage.py \
  --run-dir output/momotaro_20260110_1700 \
  --profile standard

python scripts/review-manifest-stage.py \
  --run-dir output/momotaro_20260110_1700 \
  --profile standard

# 必要なら source manifest を修正して再 review する

python scripts/review-image-prompt-story-consistency.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --set-human-review scene02_cut01 \
  --set-human-review scene02_cut02

python scripts/generate-assets-from-manifest.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --character-reference-views front,side,back \
  --character-reference-strip \
  --image-batch-size 10 --image-batch-index 1 \
  # ナレーション音声を生成しない（意図的にサイレントで進める）場合だけ --skip-audio を付ける

# 既定値:
# - video generation は 1080p
# - provider 音声は sound off（別途 narration/BGM を render で合成）
# - 画像生成前に story/script review を自動実行し、missing character_ids は補完してから進む
# - 音声生成前に narration review を自動実行し、未正規化 text や v2 非対応 tag を止める
# - 追加した無音 cut は `audio.narration.tool: "silent"` だけでなく `audio.narration.silence_contract` がないと止まる
# - story still は `still_image_plan.mode: generate_still` だけを既定で生成する
# - 両方 false の cut が残っていると画像生成は止まる
# - 両方 false の narration node が残っていると音声生成は止まる

python scripts/build-clip-lists.py \
  --manifest output/momotaro_20260110_1700/video_manifest.md \
  --out-dir output/momotaro_20260110_1700

scripts/render-video.sh \
  --clip-list output/momotaro_20260110_1700/video_clips.txt \
  --narration-list output/momotaro_20260110_1700/video_narration_list.txt \
  --out output/momotaro_20260110_1700/video.mp4

python scripts/review-video-stage.py \
  --run-dir output/momotaro_20260110_1700 \
  --profile standard
```

## state運用

- `state.txt` は追記型（最新ブロックが現在状態）
- 擬似ロールバックは「過去ブロックのコピーを末尾に追記」で再現する
- スキーマは `workflow/state-schema.txt` を参照
- 高レベルの現在地は `status=`、工程別の進行は `stage.*.status=` で読む
- `awaiting_approval` は「作業は終わったが、ユーザー承認待ちで次工程へ進めない」を意味する
- 各 stage は開始前に grounding preflight を必ず実行する
  - `python scripts/resolve-stage-grounding.py --stage research|story|script|image_prompt|video_generation --run-dir output/<topic>_<timestamp> --flow toc-run|scene-series|immersive`
  - 証跡は `logs/grounding/<stage>.json`
  - 続けて `python scripts/audit-stage-grounding.py --stage research|story|script|image_prompt|video_generation --run-dir output/<topic>_<timestamp>` を実行する
  - `logs/grounding/<stage>.readset.json` が「その stage で読むべき対象」の正本になる
- `stage.<name>.grounding.status=ready` と `stage.<name>.audit.status=passed` を確認できない限り、その stage を開始しない
- chat/manual で stage 作業を始めるときは、`python scripts/prepare-stage-context.py --stage <stage> --run-dir output/<topic>_<timestamp> [--flow toc-run|scene-series|immersive]` を標準入口として使う
- この helper は `resolve -> audit -> readset確認` を直列で実行し、`readset_path`、`grounding_report_path`、`audit_report_path`、`read_order` を含む JSON を返す
- 返ってきた `readset_path` の `global_docs -> stage_docs -> templates -> inputs` の順に読む
- stage 完了後に独立検証をしたいときは `python scripts/build-subagent-audit-prompt.py --stage <stage> --run-dir output/<topic>_<timestamp> [--flow toc-run|scene-series|immersive]` を使う
  - この script は prompt を stdout に出すだけでなく、`logs/grounding/<stage>.subagent_prompt.md` に保存し、`state.txt` に `stage.<name>.subagent.prompt=...` を追記する
  - 保存された prompt artifact をそのまま contextless subagent に渡してよい
- image prompt の意味評価を独立 subagent に任せたいときは `python scripts/build-subagent-image-review-prompt.py --run-dir output/<topic>_<timestamp> [--flow toc-run|scene-series|immersive]` を使う
  - この script は prompt を stdout に出すだけでなく、`logs/review/image_prompt.subagent_prompt.md` に保存し、`state.txt` に `review.image_prompt.subagent.prompt=...` を追記する
  - judgment subagent は content 生成や schema 判定をせず、story/script/manifest の意味整合と revision 優先度だけを見る
- run 開始時に review policy を固定する
  - `review.policy.story=required|optional`
  - `review.policy.image=required|optional`
  - `review.policy.narration=required|optional`
  - 既定は `required`
  - `--review-policy drafts` は 3 つすべてを `optional` に倒す
  - 必要なら `--story-review optional` のように個別 override する
- 物語の矛盾ソースを同一シーン/設定として混成（ハイブリッド）する場合は、確定前に人間承認を取る（運用）
  - 承認: `python scripts/toc-state.py approve-hybridization --run-dir output/<topic>_<timestamp> --note "OK"`
- 画像 prompt review の finding を人間判断で許容する場合は、対象 cut の `human_review_ok` を true にする
  - `human_review_ok: true` は subagent false を解消した意味ではなく、例外許容を記録しただけとみなす
  - その場合は `human_review_reason` に判断理由も残す
  - 例: `python scripts/review-image-prompt-story-consistency.py --manifest output/<topic>_<timestamp>/video_manifest.md --set-human-review scene02_cut01`

### 各作業で何を書くか

`state.txt` は、各作業の **開始時** と **完了時** に追記するのを基本とする。

標準 stage:

- `stage.research`
- `stage.story`
- `stage.visual_value`
- `stage.script`
- `stage.image_prompt_review`
- `stage.image_generation`
- `stage.video_generation`
- `stage.narration`
- `stage.render`
- `stage.qa`

基本ルール:

1. 作業開始時
   - grounding preflight を実行し、`stage.<name>.grounding.status=ready` を記録する
   - audit を実行し、`stage.<name>.audit.status=passed` を記録する
   - `status=...`
   - `stage.<name>.status=in_progress`
   - `stage.<name>.started_at=...`
2. 作業完了時
   - grounding が `ready` かつ audit が `passed` の stage だけ完了扱いに進める
   - 承認不要なら `stage.<name>.status=done`
   - 承認が必要なら `stage.<name>.status=awaiting_approval`
   - `stage.<name>.finished_at=...`
   - 対応する `artifact.*` / `review.*` / `eval.*` もあれば同じ block に追記
3. 作業失敗時
   - `stage.<name>.status=failed`
   - `last_error=...`
4. 作業を意図的に飛ばす時
   - `stage.<name>.status=skipped`

承認待ちが標準で発生する作業:

- 台本作成後
  - `stage.script.status=awaiting_approval`
  - `gate.script_review=required`
  - `review.script.status=pending`
- 画像作成後
  - `stage.image_generation.status=awaiting_approval`
  - `gate.image_review=required`
  - `review.image.status=pending`
- ナレーション作成後
  - `stage.narration.status=awaiting_approval`
  - `gate.narration_review=required`
  - `review.narration.status=pending`

この状態では、**次工程へ進んではならない**。

例:

- 調査開始:
  - `stage.research.grounding.status=ready`
  - `stage.research.audit.status=passed`
  - `status=RESEARCH`
  - `stage.research.status=in_progress`
- 調査完了:
  - `stage.research.status=done`
  - `artifact.research=.../research.md`
- 物語開始:
  - `stage.story.grounding.status=ready`
  - `stage.story.audit.status=passed`
  - `status=STORY`
  - `stage.story.status=in_progress`
- 台本完了（承認待ち）:
  - `stage.script.grounding.status=ready`
  - `stage.script.audit.status=passed`
  - `status=SCRIPT`
  - `stage.script.status=awaiting_approval`
  - `review.script.status=pending`
- 画像完了（承認待ち）:
  - `status=VIDEO`
  - `stage.image_generation.status=awaiting_approval`
  - `review.image.status=pending`
- ナレーション完了（承認待ち）:
  - `status=VIDEO`
  - `stage.narration.status=awaiting_approval`
  - `review.narration.status=pending`
- evaluator 実行後:
  - `eval.research.status=approved|changes_requested`
  - `eval.script.status=approved|changes_requested`
  - `eval.manifest.status=approved|changes_requested`
  - `eval.video.status=approved|changes_requested`
  - `eval.image_prompt.score=...`
  - `eval.image_prompt.unresolved_entries=...`
  - `eval.narration.score=...`
  - `eval.narration.unresolved_entries=...`
- render 開始:
  - `status=VIDEO`
  - `stage.render.status=in_progress`
- render 完了:
  - `stage.render.status=done`
  - `artifact.video=.../video.mp4`
- QA 完了:
  - `status=DONE`
  - `stage.qa.status=done`

## verify

run ごとの標準 verify:

```bash
python scripts/verify-pipeline.py \
  --run-dir output/<topic>_<timestamp> \
  --flow toc-run|scene-series|immersive \
  --profile fast|standard
```

生成物:

- `run_status.json`
- `eval_report.json`
- `run_report.md`
- `p000_index.md`

画像生成前レビューの成果物:

- `video_manifest.md` 内の `image_generation.review`
- `image_prompt_story_review.md`
