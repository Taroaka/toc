# Agent Roles & Prompts（正本）

ToC の役割を source reading、authoring、materialization、generation、ordinary validation に
分ける。担当者は canonical artifact の所有境界を守り、別の production quality 判定 worker
を起動しない。

## 実行モデル

- Codex assistant command を起点とし、Claude Code slash command は互換入口として扱う。
- L1 Run Orchestrator は p100-p900 の順序、stop target、L2 起動、required artifact existence、
  state、ordinary validator result を確認する。
- L2 P-Bucket Supervisor は一つの bucket の canonical artifact、`state.txt`、`p000_index.md`
  の single writer である。
- stage author は readset と upstream artifact を読み、isolated draft を canonical artifact に
  統合する。生成 worker は request-bound output を専用 path に書く。
- `state.txt` は append-only。派生 view は state history から再構築する。

### モデルとコンテキストルーティング

- 物語の canonical な意味、全体因果、最終統合を所有するメインモデルは
  `gpt-6-astra` とする。Story Architect と Scene Author はこの範囲に含む。
- `gpt-6-luna` は高速な枝作業専用とする。抽出、局所修復、独立検証、分類、
  大量の小さな独立タスクを受け持ち、canonical artifact の全体判断は行わない。
- Luna worker は `model=gpt-6-luna` / `fork_turns=none` で起動し、親の会話履歴を継承しない。
  枝専用の入力は path / selector / hash と
  最小限の task contract で参照し、入力本文や途中 transcript を親のコンテキストへ
  戻さない。親は最小限の result / patch / evidence summary だけを回収する。
- `gpt-6-sol` は常用しない。Luna では狭すぎ、Astra に全体を所有させるまでもない
  中間タスクに限り、orchestrator が理由と範囲を明示して選ぶ。

## 役割と責務

### Run Orchestrator（L1）

入力は user request、coarse stop target、state、navigation index、L2 result である。L1 は
bucket の存在、terminal slot、required artifact、request/provenance validator の result を確認し、
本文の品質を解釈しない。

L1 は次の順で L2 を起動する。

```text
p100 → p200 → p300 → p400 → p500 → p600 → p700 → p800 → p900
```

各 bucket の result は `logs/orchestration/pXXX.supervisor_result.json` に保存し、
`bucket`、`status`、`completed_slots`、`required_artifacts`、`state_keys`、
`output_inventory`、`next_bucket|blocked_reason` を持つ。

### P-Bucket Supervisor（L2）

L2 は stage readset を準備し、authoring worker の input/output path を決め、canonical artifact と
state を atomic transaction として更新する。L2 は schema、ID、source/reference、request、
file/decode、duration、provenance の ordinary checks を実行してから次 bucket を返す。

L2 が持つ canonical output:

- p100: `research.md`
- p200: `story.md`
- p300: `visual_value.md`
- p400: `script.md`、skeleton `video_manifest.md`
- p500: `asset_inventory.md`、`asset_plan.md`、asset request/output
- p600: production manifest、image request/output
- p700: narration/TTS request/output
- p800: video request/output
- p900: render inputs、final media、ordinary QA data

L2 は source hybridization と publication の user authorization を自動付与しない。

### Isolated Task Worker

worker には artifact path、source/readset path、目的、専用 output path を渡す。worker は
candidate、scene slice、prompt payload、request、media output、structural diagnostics を作り、
canonical artifact/state/index を直接変更しない。p400 の Scene Author など production author は
worker であっても、この境界内で authoring を行う。

## Bucket map

| Bucket | Owner output | Typical work |
| --- | --- | --- |
| p100 | `research.md` | source reading、passage/fact/uncertainty registry |
| p200 | `story.md` | Story Architect、Scene Author、causal scene sequence |
| p300 | `visual_value.md` | visual identity、anchors、asset candidates、handoff |
| p400 | `script.md`、skeleton manifest | p410 scene intent/event、p420 cut blueprint、narration draft、user changes |
| p500 | asset inventory/plan/requests | reusable character/object/location assets、reference bindings |
| p600 | production manifest/image requests | first-frame design、drawable prompt compiler、image generation |
| p700 | narration/TTS outputs | full-run text projection、TTS、measured audio timeline |
| p800 | video requests/clips | motion compiler、provider execution、frame/reference continuity |
| p900 | final render/QA data | stream normalization、ffprobe/decode/duration checks |

## Author roles

### Director / Story Architect

- 入力: `research.md` と source/readset
- 出力: `story.md` の scene ownership、order、handoff、source trace
- 参照: `docs/story-creation.md`
- 複数候補の選択は任意の user choice として保存できる。source variant の hybridization は
  explicit authorization を要求する。

### Scene Author

- 入力: Story Architect の scene slice、前後 handoff、source registry
- 出力: `scene_draft_v1`（scene intent、event beats、start/end state、reveal、preservation）
- `event_id`、`beat_id`、`evidence_id`、`role_id`、`character_id`、`handoff_anchor_id`
  は source contract に登録された ID を exact に使う。
- contract ownership、canonical order、reveal state、source digest を変更しない。
- provider prompt、camera、lens、固定 cut 数を story scene に混ぜない。
- output 後は ordinary `authoring_preflight` で ID、順序、coverage、handoff、source evidence を
 確認する。

### Visual Value Ideator

- 新規runは `docs/implementation/visual-planning.md` のsource_first_v2を使う。
  全文のresearch/storyに基づいて必要なnotesだけを執筆し、追加判断がなければ空配列を返す。
  下記のanchor/reference/asset候補は必要な場合の検討事項であり、全欄を埋める義務ではない。

- 入力: `research.md`、`story.md`
- 出力: `visual_value.md`
- visual identity、scene visual value、anchor/reference strategy、asset candidates、
  regeneration risks、p400-p700 handoff を定義する。
- p300 では provider prompt、request、asset image、motion prompt を生成しない。
- `workflow/visual-value-template.yaml` を参照する。

### Scriptwriter

- 入力: `story.md`、`visual_value.md`、scene plan
- 出力: `script.md` と skeleton `video_manifest.md`
- `p410` で scene intent/event、`p420` で cut blueprint、`p440` で supplied user changes、
  `p450` で skeleton manifest を作る。
- `docs/script-creation.md` と provider-specific playbook を読む。

### Asset Author / Runner

- 入力: script、story、visual value、source/readset
- 出力: asset inventory、asset plan、immutable request、reusable asset files
- asset IDs、reference paths、prompt/settings、source digest、output provenance を一方向に束縛する。
- `workflow/asset-plan-template.yaml` と `docs/implementation/asset-bibles.md` を参照する。

### Image Prompt Author / Runner

- 入力: scene event、cut contract、asset/reference bindings
- 出力: first-frame visual plan、drawable prompt IR、image API payload、request snapshot、image file
- provider-facing prompt には drawable state と許可 constraints だけを送る。
- request-bound provenance、bytes hash、destination、file/decode checks を保存する。

### Narration Writer / TTS Runner

- 入力: script narration、manifest cut order、pronunciation dictionary
- 出力: continuous narration、narration spans、TTS text、audio candidates、measured duration
- `script.md` が text source of truth、`tts_text` は provider projection である。
- `human_locked` text を user が明示した場合は保持し、変更には新しい request revision を使う。
- candidate listening/selection は optional user action であり、選択後に hash/provenance を検証する。

### Video Prompt Author / Runner

- 入力: cut contract、first/last frames、ordered references、provider settings
- 出力: compiled video payload、request snapshot、video clip、provenance record
- `video_prompt_projection_registry_v5` と `conditional_video_prompt_compiler_v5` を使う。
- provider capability、motion boundary、frame/reference hashes、prompt/source digest を検証する。

### Render / QA Operator

- 入力: active clip list、audio timeline、render units
- 出力: normalized streams、`video.mp4`、ordinary QA data
- ffprobe、decode、duration、aspect ratio、audio sync、subtitle、file existence を確認する。
- QA data は measured values と processing errors を記録し、品質 score を計算しない。

### YouTube Thumbnail Prompt Writer

- 入力: topic、存在すれば story/visual/video manifest
- 出力: 画像生成 API を呼ばない thumbnail prompt
- 16:9、高コントラスト、スマホ視認性、背景と文字造形を指定する。

### Scene Evidence Researcher / Scene Scriptwriter

scene-series flow では evidence researcher が source question と evidence を整理し、scene
scriptwriter が 30–60 秒の scene script を作る。各 output は source IDs、scene selectors、
narration/image/video handoff を持ち、通常の structural validator を通す。

## Prompt packet

各 worker へ渡す packet は会話履歴を前提にしない。

```yaml
prompt_packet:
  schema_version: toc_authoring_prompt_packet_v1
  role: story_architect|scene_author|scriptwriter|asset_author|image_author|narration_writer|video_author
  stage_readset:
    required_docs: []
    required_templates: []
    source_artifacts: []
  source_bindings:
    - path: research.md
      sha256: sha256:<hex>
  input_selectors: []
  output_contract: ""
  output_path: scratch/worker-output.json
```

worker は output path に artifact を書き、L2 が schema/ID/reference/provenance checks を通して
canonical artifact へ統合する。

## Grounding and citations

Research output は source passage、source URL/path、retrieval date、uncertainty、confidence、
fact/interpretation boundary を保持する。Story/script は source IDs を参照する。Asset/image/video
prompt は source meaning を provider-facing prose に直接漏らさず、compiled visible state へ投影する。

## Versioning

Role format は `role@vX.Y.Z`。role prompt の変更は canonical docs と対応する Claude/Codex
mirror を同時に更新する。
