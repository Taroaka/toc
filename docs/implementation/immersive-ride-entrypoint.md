# Entrypoint（/toc-immersive-ride）仕様（正本）

Codex assistant command を起点に、topic/source から没入型の実写 cinematic video run を作る。
Claude Code slash command は互換入口として扱う。

## 1. Command

```text
/toc-immersive-ride --topic "桃太郎"
/toc-immersive-ride --topic "かぐや姫" --stage p300 --experience cinematic_story
/toc-world-walk --source-run output/桃太郎_<timestamp>
```

arguments:

- `--topic`: 必須
- `--source-run`: `world_walk` では必須
- `--dry-run`: provider call をせず materialization/structural checks を行う
- `--config`: config override
- `--stage`: default `video`。coarse target は active bucket の最後まで進む
- `--experience`: `cinematic_story|cloud_island_walk|world_walk|ride_action_boat`
- `--target-duration-seconds`: 300–1200、default 300

active target map:

```text
p100→p120  p200→p220  p300→p330  p400→p450  p500→p570
p600→p680  p700→p750  p800→p840  p900→p920
```

p410/p420 は authoring slots。p400 では scene/cut structure を作り、p450 で skeleton
manifest を materialize する。asset/image、TTS、video、render は後続 bucket で行う。

## 2. Run artifacts

```text
output/<topic>_<timestamp>/
  state.txt
  p000_index.md
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
  logs/grounding/
  logs/orchestration/
  logs/validation/
```

`state.txt` は append-only。source bytes/hash、stage status、slot status、artifact digest、
request revisions、provider provenance、ordinary validation results を記録する。

## 3. Experience rules

共通:

- photorealistic/cinematic/live-action の実写系表現を使う
- 画面内 text、字幕、logo、watermark を生成 prompt に入れない
- 1 cut は一つの primary intent を持つ
- character/object/location identity と time/time-of-day を manifest で固定する
- 画像、音声、動画 provider output は request-bound provenance を持つ

`cinematic_story`:

- POV/三人称は scene intent に応じて選べるが、1 cut 内の視点は固定
- 物語 character や主役級 object を continuity anchor にする
- scene IDs は manifest 順に処理し、数値の連番を仮定しない

`cloud_island_walk`:

- anchor、道/橋/階段などの前進導線、物理メタファを scene contract に書く
- 文字で概念を説明せず、形、光、距離、動きで示す

`world_walk`:

- source run の `story.md`、`assets/`、source asset IDs を参照し、source run path を記録
- 観察者 POV で source character 本人の視点へ置き換えない
- source asset の identity を保ち、既存 asset と参照 bytes を request に束縛する

## 4. Generation flow

```text
source context → research → story → visual value → script
  → skeleton manifest → asset plan/generation
  → scene image generation → narration/TTS
  → motion/video generation → stream normalization/render → ordinary QA
```

画像:

- Codex built-in image generation（`codex_builtin_image` / `gpt-image-2`）
- reusable assets は `asset_plan.md` に stable IDs と output path を持つ
- scene image は `scene_event → cut_contract → first_frame_visual_plan →
  drawable_prompt_ir → image_api_prompt_v2` を通る
- provider prompt、request snapshot、reference bytes hash を保存する

音声:

- ElevenLabs
- `script.md` が readable narration と `tts_text` の source
- candidate listening/selection/editing は任意の user action
- TTS output を実測し、intentional silence の reason/duration とともに audio timeline を作る

動画:

- Kling 3.0/Omni または Seedance
- `cut_contract → video_prompt_ir → video_api_prompt_v1` を通る
- first/last frame、ordered references、provider capability、prompt/source hashes を保存する
- materialize した payload と current design が一致する場合だけ provider を呼ぶ

## 5. Structural validation

stage 間で次を確認する。

- schema、types、enum、unique IDs
- source/asset/selector/location/handoff reference
- event ordering、reveal boundary、first-frame/motion boundary
- manifest/script selectors と target duration
- request snapshot、prompt/source/provider hash
- output existence、file type、decode、duration、stream compatibility、provenance

壊れた input、missing reference、hash drift、decode failure、runtime transport failure は該当
item の processing error として停止し、source artifact を修正して再実行する。

## 6. Optional user actions

candidate の選択、listening、image/narration editing、change request は任意である。
`human_choice.*` に actor、timestamp、selector、revision、description を記録し、変更後に
structural/request/provenance checks を再実行する。

contradictory source variants の hybridization と publication は、別々の明示 user action として
保存する。どちらも生成の代替結果として扱わない。

## 7. State and resume

resume は同じ run の append-only state に新しい delta を追加する。upstream digest が変わった
downstream item だけを stale にして再 materialize/re-generate し、valid output は完全な binding
が一致する限り保持する。run lease と destination lock を使って concurrent mutation を防ぐ。

## References

- docs/data-contracts.md
- docs/how-to-run.md
- docs/implementation/video-integration.md
- docs/implementation/image-prompting.md
- workflow/video-manifest-template.md

