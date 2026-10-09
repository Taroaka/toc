# Orchestration / QA / Compliance / Publishing

本書は、research、story、script、asset、image、narration、video、render を一つの運用として
接続する。production は直接 authoring → ordinary structural validation → generation の順で進み、
品質を採点する production worker や必須の人間承認 artifact を持たない。

## 1. Orchestration

### 1.1 ステートマシン

```text
INIT → RESEARCH → STORY → VISUAL_VALUE → SCRIPT → ASSET
     → SCENE_IMPLEMENTATION → NARRATION → VIDEO → RENDER → QA
     → PUBLISH → ANALYZE → IMPROVE → DONE
```

入力は exact source、topic、experience、target duration、provider/runtime options である。
run は `output/<topic>_<timestamp>/` に作成し、最初に
`logs/orchestration/create_input.json` へ入力 identity と source SHA-256 を保存する。

### 1.2 バケット所有権

- L1 Run Orchestrator は bucket 順、coarse stop target、L2 起動、required artifact の存在、
  state、ordinary validator result を確認する。本文の品質判定はしない。
- L2 P-Bucket Supervisor は一つの bucket の canonical artifact、`state.txt`、
  `p000_index.md` を single writer として更新する。
- stage author は source/readset を読み canonical artifact を作る。孤立 worker は candidate、
  temporary、media output を自分の専用 path にだけ書く。
- bucket 完了時は `logs/orchestration/pXXX.supervisor_result.json` に
  `status`、`completed_slots`、`required_artifacts`、`state_keys`、
  `output_inventory`、`next_bucket|blocked_reason` を記録する。

### 1.3 Source context と普通の検証

stage 開始時に `prepare-stage-context.py` で required docs、templates、upstream inputs を
解決する。返された readset の順序は `global_docs → stage_docs → templates → inputs`。
これは authoring の入力を決める処理で、品質の証明書を生成する処理ではない。

各 stage は次を検証してから次へ渡す。

- YAML/JSON/Markdown の schema、型、必須値、unique ID
- source、selector、path、scene/cut/event、handoff の参照解決と順序
- manifest と script の selector 一致、target duration、provider capability
- prompt/request snapshot、settings、first/last frame、ordered reference、source digest
- generated file の存在、file type、decode、duration、audio/video stream、request provenance

壊れた入力、欠落参照、hash drift、出力欠落、decode failure、runtime transport failure は
その stage の processing error として停止する。別の content verdictへ変換しない。

### 1.4 Frontend create

`/api/image-gen/runs/create` は CLI と同じ backend helper を呼び、source/request identity、
stage artifacts、structural validation、provider request binding を同じ形式で materialize する。
frontend だけの scaffold、暗黙の policy fallback、別の prompt compiler は作らない。

candidate の image/audio/video をユーザーが選ぶ、聴く、編集する、change request を出す、
という UI は任意である。選択や編集は `human_choice.*` として保存し、request revision を
変えた後に普通の構造・参照・provenance 検証を再実行する。

### 1.5 Resume

resume は同じ run directory で行い、append-only state history を改変しない。upstream digest
または source/request identity が変わったら downstream artifacts を stale として扱い、
必要な最小 item だけを再 materialize / 再生成する。既存の valid output は bytes と
provenance が一致する限り保持する。

## 2. Production order

```text
SCRIPT:
  scene/cut/narration authoring → skeleton manifest materialization → structural checks

ASSET:
  asset inventory → asset plan → request snapshot → reusable asset generation → file checks

SCENE_IMPLEMENTATION:
  production manifest/prompt authoring → request snapshot → scene still generation → file checks

NARRATION:
  TTS text authoring → candidate generation/listening (optional) → audio generation
  → measured duration and timeline checks

VIDEO:
  motion contract authoring → request snapshot → clip generation → frame/reference checks

RENDER:
  stream normalization → clip/audio combine → final media checks → QA data

PUBLISH:
  explicit user publication authorization → selected output handoff
```

### 2.1 p400 scene/cut authoring

`p410` owns scene intent/event sequence and `p420` owns cut blueprints. The authoring contract
requires exact event beat IDs, one primary cut intent, visible evidence, first-frame state, motion
boundary, narration boundary, asset dependencies, and next-stage handoff. The structural validator
checks those relationships before `p450` creates the skeleton manifest.

### 2.2 p500/p600 asset and image

Asset identity is defined once in `asset_plan.md`. Image prompts are compiled from
`scene_event → cut_contract → first_frame_visual_plan → drawable_prompt_ir`. The saved payload
and immutable request snapshot are the execution source. Provider prose contains only drawable
content and permitted constraints.

### 2.3 p700 narration

`script.md` is narration source of truth. `tts_text` is a provider-specific projection and
may use the pronunciation dictionary. The audio timeline sums measured spoken audio and explicitly
declared intentional silence. Candidate listening and text editing are user choices; no pass field
is required.

### 2.4 p800/p900 video and render

The video compiler binds motion to the current first frame, last frame, ordered references, provider
settings, and exact prompt hash. Render normalizes all streams before concatenation, then checks
ffprobe output, file existence, audio sync, target aspect ratio, and subtitle files.

## 3. QA

QA records ordinary operational facts:

```yaml
qa_checks:
  source_ids_resolved: true
  selectors_unique: true
  request_hashes_current: true
  output_files_decodable: true
  audio_video_streams_compatible: true
  duration_measured: true
  provenance_matched: true
```

A QA record may list errors, warnings, measured values, and remediation targets. It does not produce a
quality score, rubric, threshold, or required production certificate. Repair means editing the owning
canonical artifact and rerunning the relevant structural checks.

## 4. Compliance

Compliance remains a separate rights, safety, and data-use concern:

```yaml
compliance_rules:
  copyright:
    prohibit_direct_copy: true
    require_source_tracking: true
  likeness:
    real_person: consent_required
    public_figure: caution_required
  data_usage:
    training_opt_out: respect
    api_terms: enforced
  disclosure:
    ai_generated_notice: true
```

Compliance logs may contain an actor, decision, source, and timestamp. These records do not decide
whether a production artifact is aesthetically good.

## 5. Publishing and improvement

Publishing is a separate user-authorized operation. Store the selected output, destination, account,
publication authorization, and publication result. Analytics can record view duration, retention,
likes, comments, shares, and subscriber changes.

An improvement proposal may use output and analytics data to suggest a future authoring change. It
does not mutate a completed run or gate the current generation.

## 6. Directory layout

```text
output/<topic>_<timestamp>/
  research.md
  story.md
  visual_value.md
  script.md
  video_manifest.md
  asset_inventory.md
  asset_plan.md
  assets/
  audio/
  video.mp4
  state.txt
  p000_index.md
  logs/grounding/
  logs/orchestration/
```

## 7. Minimal implementation

```text
1. Save create input and resolve source context.
2. Author research and story.
3. Author visual value, scene/cut script, and skeleton manifest.
4. Run ordinary structural validation.
5. Materialize asset/image/audio/video requests and generate outputs.
6. Normalize and render the final media.
7. Run file, stream, duration, and provenance checks.
8. Ask for explicit publication authorization when publishing is requested.
```


### Codexスレッドで採用された素材の正式反映

ユーザーが対象を明確にして「良い」「OK」「合格」「これでいこう」「反映してよい」と伝えた場合、担当エージェントは、その素材を対象物語へ正式採用する。画像、動画、ナレーション/台詞音声、SE、BGMが対象。これは毎回の生成に承認を必須とする規則ではなく、ユーザーが選んだ成果物を一時保存のまま放置しないための規則である。

1. 会話と生成履歴から対象run、scene/cutまたはsound cue、採用する版を特定する。複数候補のうち対象が不明な場合だけ質問し、特定できる素材は先に反映する。単なる作業方針への「OK」を、未提示の全候補の採用に広げない。
2. tmp、スレッド専用領域などrun外の素材は、既存runの保存規約に従い`assets/`配下へコピーする。画像、動画、audio、sound等の既存構成に合わせ、名前またはhashで衝突を避ける。既にrun内にあるファイルは重複コピーせず利用する。元ファイルを先に削除しない。
3. ファイル存在、コピー前後のhash、画像decode/音声動画decode、必要な尺/解像度を確認する。プレビュー用の連結音声や静止画動画を、個別cut音声や生成動画として誤登録しない。
4. 既存のcandidate選択/取込処理を優先し、manifestの正式なoutput参照・候補選択・音声/BGM/SEの配置データを更新する。ファイル保存だけで終了しない。run相対パスを使い、UIと後続renderがその素材を参照することを確認する。
5. 採用記録にはユーザーの発言、日時、run/item、元と保存先、hash、候補ID・原稿/request revision、利用できる生成履歴を残す。承認対象の生成時原稿と現行原稿が違う場合は差を明示し、hashや生成履歴を捏造して現行版に合わせない。必要なら承認済みの外部素材として保存し、現行cutへの紐付けを未完として記録する。
6. stateは過去を上書きせず、`toc.state_store`または既存state更新helperで追記し、current state・run_status・indexの表示へ反映する。完了できたitemは完了と記録する。工程全体の`done`は、その工程で必要な全itemの保存・参照・通常の検証が揃った場合だけ付ける。部分採用の場合は完了itemと残件を記録し、工程全体は進行中に保つ。
7. 画像/音声/動画/SE/BGMはそれぞれの生成・採用・配置・mix/render工程を区別する。BGMを選んだだけでmix完了、1cut動画を選んだだけで全編動画完了にはしない。素材差し替えが後続出力を古くする場合は影響範囲だけを未完へ戻す。
8. 採用が完了した素材を再開処理で不要に再生成しない。再実行は同じ候補/hashなら重複保存・重複採用をしない。既存の合格素材と無関係な工程状態を保つ。
9. 返信では保存/正式参照への反映、更新した工程state、残件を簡潔に伝える。実際に完了していない工程を「終わった」ように表示しない。
