# Image Prompting（Codex built-in image / cross-model）: 正本

このドキュメントは **画像生成プロンプト品質**をシステムの根幹として扱い、
`video_manifest.md` の `scenes[].image_generation.prompt` を「全体 → 個別」の順で安定して組み立てるための正本。
ただし、**全scene/cutに新規の生成静止画が必要とは限らない**。新規生成は、同じ場所/物体/人物状態の continuity anchor を初めて作るとき、または複数scene/cutで再利用する参照画像が必要なときに優先する。

画像生成の正解は、**「うまい一文を書く」ことではなく、構造化して anchor を決め、reference を固定し、manifest を直接レビューし、story/script と矛盾していないか確認してから回すこと**である。

画像生成の既定順は、**asset stage → cut stage** の 2 段とする。

- asset stage
  - `asset_plan.md` を作る
  - `script.md` の該当箇所を見て reusable asset を設計する
  - human review を通してから asset を生成する
  - provider は参照あり/なしを問わず `tool: codex_builtin_image` に固定する
  - `reference_inputs[]` が無い asset だけは `execution_lane=bootstrap_builtin` の no-reference lane として扱う
- cut stage
  - 既存どおり `video_manifest.md` を直接 review し、`image_generation.review` に結果を書き戻す
  - review は単なる missing character 検出ではなく、prompt が環境寄りに流れすぎていないか、story 上の関係性/行為が抜けていないかも確認し、足りない `character_ids` は先に補完する
  - 各 cut の review 状態は `agent_review_ok` と `human_review_ok` を持ち、さらに **false 理由 key** を明示する
  - canonical field 名は `agent_review_reason_keys` とし、現行の `agent_review_reason_codes` は互換 alias として扱う
  - criterion score は `rubric_scores`、加重合計は `overall_score` に残す
  - **両方 false の cut が残っている限り画像生成には進まない**
  - **prompt 本文に人物が出ているのに `image_generation.character_ids` が空の entry は review fail** とする
  - 人物参照は自然言語だけに頼らず、manifest の `character_ids` で明示する

対象:
- `/toc-immersive-ride` の `video_manifest.md`
- scene-series / 通常 run の `video_manifest.md`（静止画生成）

除外:
- アニメ/イラスト調の最適化
- Midjourney 専用構文（`--ar` など）に依存したテンプレ

---

## 結論（最短の型）

**prompt は 1本の自由文にせず、毎回同じ見出し順で書く。**

scene image prompt は、scene の説明文ではなく、**cut の映像が始まる直前に観客が見る映画的な still** として書く。
その still は、単に美しい背景ではなく、`scene_contract` の `dramatic_question`、`value_shift.visible_evidence`、`causal_turn`、`visual_thesis` のどれかを画面上で読めるようにする。

最短の変換順:

1. `script.md` の `scene_intent` を読む。
2. `cut_blueprint.target_beat` と `visual_beat` を読む。
3. `must_show` を、人物・場所・道具・行為・光・構図に翻訳する。
4. `first_frame_brief` を、API に渡せる「見えている状態」へ書き換える。
5. `character_ids` / `object_ids` / `location_ids` と reference を確認する。
6. 6 block prompt に落とす。

`motion_brief` は p800 動画生成の入力であり、p600 の画像 prompt 作成では参照しない。
画像生成 provider に渡すのは、動画開始前に見えている状態までである。
「このあと何が動くか」を先に読ませると、静止画が action 完了後の絵へ寄りやすい。


prompt 本文は画像生成 provider がそのまま描ける語だけで構成する。`物語「シンデレラ」の scene10`、`この画像は物語「シンデレラ」の一場面`、`scene10_cut01` のような制作管理メタ情報は書かない。必要なのは `シンデレラの灰の台所`、`灰の残る古い台所で暖炉の灰を掃くシンデレラ` のような、画面に現れる具体語である。provider 固定の判断は request metadata / 設計書に置き、prompt 本文には書かない。

さらに、正しい順番は「うまい一文を書く」ではなく、
**構造化する → anchor を決める → reference を固定する → manifest をレビューする → story/script 整合を確認する → 画像生成する** である。
camera は `30mm` のような数値単独で止めず、`広め / 中広角 / 寄り` と `前景 / 中景 / 背景`、そして「何を読ませるか」まで書く。

加えて運用順は次の通り。

0. asset stage が必要な run では、先に `asset_plan.md` を review / approve して reusable asset を作る
0.1. image request は参照あり/なしを問わず `tool: codex_builtin_image` を使う。no-reference image request だけ `execution_lane=bootstrap_builtin` として互換 lane に寄せる
1. `still_image_plan` で新規生成対象を確定する
2. `python scripts/review-image-prompt-story-consistency.py --manifest output/<run>/video_manifest.md --fix-character-ids` で story/script 整合を確認し、不足 `character_ids` を補完する
3. review 結果で問題がある cut は `image_generation.review.agent_review_ok: false` になり、理由は `agent_review_reason_keys`（または互換 alias の `agent_review_reason_codes`）に残る
4. rubric の各軸 `story_alignment` / `subject_specificity` / `prompt_craft` / `continuity_readiness` / `first_frame_readiness` / `production_readiness` を見て、弱い軸から直す
5. false reason に対応する fix を manifest に反映する
6. fix 後に再 review して finding が消えた cut は、subagent が `agent_review_ok: true` に戻す
7. 人間が issue を理解したうえで例外許容して進める cut だけ `python scripts/review-image-prompt-story-consistency.py --manifest output/<run>/video_manifest.md --set-human-review scene02_cut01` のように `human_review_ok: true` を付け、判断理由も残す
8. manifest review を通してから、初めて画像生成を回す

補足:
- 関数 review は hard gate を優先する。missing contract / missing ids / required prompt block 欠落 / reveal 破り / self-contained 違反のような構造問題は `agent_review_ok: false` に直結させる
- `must_avoid` の単純文字列一致、`target_focus` の語一致、`production_readiness` の弱さは warning として残してよい
- それらの warning を別コンテキストで総合判断したいときは `scripts/build-image-prompt-judgment-review.py` で `logs/review/image_prompt.judgment_prompt.md` を生成し、contextless subagent に judgment review を依頼する

## Source priority（どの正本をどう読むか）

画像生成は `script.md` と `video_manifest.md` を併読するが、役割は同じではない。

- 主参照: `video_manifest.md`
  - `scene_contract`
  - `image_generation.prompt`
  - `still_assets[]`
  - `reference_usage[]`
  - `location_ids[]`
- 補助参照: `script.md`
  - `visual_beat`
  - `human_review.approved_visual_beat`
  - `approved_image_notes[]`
  - `human_change_requests[]`

原則:

- `script.md` は image prompt そのものではない
- `script.md` は「何を見せるべきか」の意味設計を持つ
- `video_manifest.md` は「どう生成するか」の実装設計を持つ
- `narration` と `tts_text` は補助参照に留める
- 特に `tts_text` は TTS 専用であり、image generation の主ソースにしない

location 参照の使い分け:

- 同じ場所の昼夜差分、現在/未来差分、状態違いは main anchor から派生させる
- ただし、同一建築内でも物語上は別エリアなら別 `location_anchor` にする
- 例: 宴会エリアそのものと、宴会エリアが奥に見える foyer は別 asset
- foyer から宴会エリアを見せたい場合は、`derived_from` ではなく `reference_usage.mode=background_glimpse` で表現する
- 要するに、同一場所の状態差分は派生、別エリアの見え関係は参照で扱う

したがって、人レビューがナレーション review の段階で

- どの画像を参照するか
- 背景としてだけ使うか
- 先に別 asset を作ってから派生を作るか

まで指示した場合でも、その正本は `script.md` に残し、生成実行前に `video_manifest.md` の `still_assets[]` / `reference_usage[]` / `image_generation.*` へ materialize してから使う。

## Review lifecycle（manifest 契約）

この契約は Urashima 専用ではなく repo 全体に適用する。各 `image_generation.review` は、少なくとも次の review field を明示する。

```yaml
contract:
  target_focus: "character|relationship|setpiece|blocking|environment"
  must_include: []
  must_avoid: []
  done_when: []
agent_review_ok: false
agent_review_reason_keys:
  - missing_story_action
  - camera_or_composition_under_specified
rubric_scores: {}
overall_score: 0.0
human_review_ok: false
human_review_reason: ""
human_review:
  status: "pending|approved|changes_requested"
  notes: ""
  change_requests: []
```

補足:

- 現行表記として `agent_review_reason_codes` を使っていてもよいが、意味は `agent_review_reason_keys` と同じに保つ
- `agent_review_reason_summary` は任意の補助説明であり、reason key の代替にはしない

意味:

- `agent_review_ok`
  - subagent が「この entry は story/script/reference 契約を満たしている」と判定したときだけ `true`
  - 不足がある間は `false`
- `agent_review_reason_keys`
  - `agent_review_ok: false` の根拠
  - false のときは 1 つ以上必須
  - fix 完了後は空配列に戻してよい
- `rubric_scores`
  - criterion score
  - `story_alignment` / `subject_specificity` / `prompt_craft` / `continuity_readiness` / `first_frame_readiness` / `production_readiness`
- `overall_score`
  - rubric score の加重合計
- `human_review_ok`
  - 人間が finding を理解したうえで例外許容した記録
  - subagent finding を消した意味にはしない
- `human_review_reason`
  - 人間 override の理由
  - `human_review_ok: true` のときは必須
- `human_review`
  - 通常の human feedback loop の記録
  - `change_requests[]` は reviewer が prompt 修正を要求した本文
  - `human_review_ok` の代替にしない

既定の reason key:

- `source_anchor_missing_from_prompt`
- `missing_character_id`
- `missing_object_id`
- `prompt_only_local_mismatch`
- `prompt_contains_nonvisual_metadata`
- `prompt_contains_first_frame_metadata`
- `prompt_leaks_motion_brief`
- `prompt_missing_expected_character_anchor`
- `prompt_missing_expected_object_anchor`
- `prompt_subject_drift`
- `blocking_drift`
- `missing_required_prompt_block`
- `prompt_not_self_contained`
- `non_japanese_prompt_term`
- `prompt_mentions_character_but_character_ids_empty`
- `image_contract_missing`
- `image_contract_must_include_unmet`
- `image_contract_must_avoid_violated`
- `image_contract_target_focus_unmet`
- `image_prompt_story_alignment_weak`
- `image_prompt_subject_specificity_weak`
- `image_prompt_prompt_craft_weak`
- `image_prompt_continuity_weak`
- `image_prompt_not_first_frame_ready`
- `image_prompt_first_frame_readiness_weak`
- `image_prompt_production_readiness_weak`
- `prompt_missing_scene_turn`
- `prompt_lacks_visual_evidence`
- `prompt_lacks_attention_hierarchy`
- `prompt_finishes_action_in_still`
- `prompt_missing_cut_function`

運用ルール:

1. subagent は不足を見つけた entry を `agent_review_ok: false` にする
2. subagent は false 理由を `agent_review_reason_keys` に残す
3. fix 可能なものは manifest 側へ反映する
4. fix 後に subagent が再 review し、解消した entry は `agent_review_ok: true` に戻す
5. 未解消 finding を人間判断で許容する場合だけ、人間が `human_review_ok: true` と `human_review_reason` を記録する
6. reviewer が差し戻す場合は `human_review.status=changes_requested` とし、論点ごとに `human_review.change_requests[]` を残す

推奨 `human_review.change_requests[]`:

```yaml
- request_id: "hr-001"
  status: "open|accepted|rejected|deferred|resolved"
  category: "story_alignment|reveal|subject_specificity|continuity|craft|other"
  requested_change: ""
  rationale: ""
  proposed_patch: ""
  requested_at: "ISO8601"
  resolved_at: ""
  resolution_notes: ""
```

高度な修正要求は `still_assets[]` と `reference_usage[]` へ materialize する。

- `still_assets[]`
  - `asset_id`, `role`, `output`, `image_generation`
  - `derived_from_asset_ids[]`, `reference_asset_ids[]`
  - `reference_usage[]`, `direction_notes[]`, `applied_request_ids[]`
- `reference_usage[]`
  - `mode: same_subject|same_camera|background_glimpse|foreground_anchor|style_anchor|lighting_anchor|state_transition`
  - `placement: foreground|midground|background|offscreen_implied`

例:

- 「1枚目を作って、その画像を参照して 2 枚目を作る」
  - `derive_still_asset`
- 「宴会エリアを奥に見える背景として使う」
  - `reference_usage.mode=background_glimpse`
- 「同じ場所 asset を別 cut でも使う」
  - `assets.location_bible[]` + `image_generation.location_ids[]`

asset stage での参照原則:

- character variant は main character を参照してよい
- same-camera / state-transition still は base still を参照してよい
- same-location の昼夜差分 / 現在未来差分は base location を参照してよい
- それ以外の独立 location anchor は、使用 cut があっても `reference_inputs[]` を空にする
- 別エリアから他エリアを見せる場合は、asset stage ではなく cut stage の `reference_usage.background_glimpse` で扱う
- p500 / p600 の image request は `tool: codex_builtin_image` で固定する
- `reference_count == 0` の request は `execution_lane=bootstrap_builtin` の no-reference lane にする
- `reference_count > 0` の cut image は `execution_lane=standard` に残すが、実行 provider は `codex_builtin_image` のまま変えない
- 画像成果物は実写系（photorealistic / cinematic / live-action）を必須とする。手続き生成したローカル PNG、placeholder PNG、ベクター風/イラスト風/低情報量 raster は、形式が PNG/JPEG でも canonical p500/p600 output として採用しない
- `logs/image_generation_prompts.jsonl` に Codex app-server 由来の生成証跡がない画像、または `source=local_raster...` の画像は hard fail とし、再生成する

<!-- image-gen-setting:scene:start -->
scene image prompt は、動画を始める最初の1フレームとして書く。
`[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`, `[連続性]`, `[禁止]` の順を守り、他 cut や前後 prompt の記憶に依存しない。
参照画像がある場合は、metadata の reference path ではなく、人物参照画像 / 小道具参照画像 / 場所参照画像として何を維持するかを本文に書く。
場面名は、内部 selector ではなく API が描ける具体語にする。例: `scene10` ではなく `シンデレラの灰の台所`、`物語「シンデレラ」の scene10` ではなく `灰の残る古い台所で暖炉の灰を掃くシンデレラ`。
<!-- image-gen-setting:scene:end -->

subagent review の必須 criterion:

- `[全体 / 不変条件]`
- `[登場人物]`
- `[小道具 / 舞台装置]`
- `[シーン]`
- `[連続性]`
- `[禁止]`

上記 6 block のいずれかが欠けている prompt entry は、内容の良し悪し以前に設計違反として `agent_review_ok: false` にする。reason key は `missing_required_prompt_block` を使い、必要なら補助説明で欠けた block 名を列挙する。

独立性 criterion:

- 画像生成 AI は stateful ではない前提で扱う
- prompt 本文で `scene03_cut01` のような他 cut 参照をしない
- `前カット`, `次カット`, `前scene`, `次scene`, `前のprompt` のような参照依存表現を使わない
- `[連続性]` には「この画像 / この場面で何が読み取れるべきか」を書き、別 prompt の記憶を前提にしない
- 有効な関連性は、`references` に入った画像に対して「その画像の誰/場所/小道具が、この場面でどう現れるか」を明示する形で書く
- 画像参照を伴わない continuity 指示は、設計意図としては有っても request 本文では弱い
- request 本文では `cut` のような運用メタ語を避け、「この場面」「この画像」を使う
- request 本文では `物語「<topic>」の sceneXX`、`この画像は物語「<topic>」の一場面`、`[物語の文脈]` のようなメタ説明を使わない
- 作品文脈が必要な場合も、タイトルだけで説明せず、人物・場所・道具・行為に落とす。例: `シンデレラの灰の台所`、`王宮の階段に残された片方のガラスの靴`
- 英語の混在語 `rideable` は使わず、日本語の `騎乗可能` などへ統一する
- prompt 本文に人物名があるのに `image_generation.character_ids` が空なら `prompt_mentions_character_but_character_ids_empty` として false にする

cinematic craft criterion:

- 6 block が存在しても、各 block が薄い定型句だけなら合格にしない
- scene image prompt 本文は、空白除去後 220 文字以上を目安にする
- subject / blocking / setting / light / camera / material のうち 4 系統以上の具体要素を含める
  - subject: 人物、顔、表情、視線、手、姿勢
  - blocking: 前景、中景、背景、距離、向き、手前、奥、斜め、並び
  - setting: 部屋、道、森、海、城、台所、庭、階段、床、壁、窓、扉
  - light: 光、影、逆光、月明かり、朝日、夕暮れ、反射、陰影
  - camera: 構図、クローズアップ、広角、俯瞰、ローアングル、焦点、被写界深度
  - material: 質感、布、木、石、金属、ガラス、埃、灰、水滴、しわ、擦り傷
- 抽象語（例: 願い、真夜中、孤独、運命）を `must_include` にする場合は、その抽象語が画面上の物体・姿勢・光・空間配置としてどう見えるかまで prompt 本文へ翻訳する
- この criterion を満たさない場合は `image_prompt_prompt_craft_weak` を付ける

非視覚メタデータ criterion:

- prompt が API に理解できない制作管理語で scene を説明している場合、subagent は `agent_review_ok: false` にする
- 対象例: `物語「シンデレラ」の scene10`、`scene10_cut01`、`この画像は物語「シンデレラ」の一場面を視覚化する`、`[物語の文脈]`
- この場合の canonical reason key は `prompt_contains_nonvisual_metadata`
- 修正時は、scene id を単に削るのではなく、物語上の具体名・場所・行為へ置き換える

still 生成の既定実行対象:

- story cut は `still_image_plan.mode: generate_still` のものだけを既定で生成する
- `reuse_anchor` と `no_dedicated_still` は、明示的に `--image-plan-modes` を広げない限り生成しない
- `assets/characters/*` と `assets/objects/*` の reference 画像は `still_image_plan` に関係なく既定対象に含める
- request file には review 用に image prompt を持つ全 scene/cut を出す
  - `still_mode` は設計上の扱い
  - `generation_status` は `missing|created|recreate`
  - `recreate` のときだけ `--force` で既存 canonical を `assets/test/` に退避してから再生成する
- request review では prompt 以外の判断材料も凍結する
  - explicit `references`
  - `character_ids` / `object_ids` / `location_ids` から解決される asset reference
  - 生成時に AI が「どの asset を参照すべきか」をその場で補完しない状態を目指す
- request metadata の `references` は path を保持するが、本文では path を直接書かない
  - 本文では `人物参照画像1`, `場所参照画像1`, `小道具参照画像1` のような役割付きラベルを使う
  - 複数ある場合も metadata の並び順で番号を固定する
- `references` が空なら `[参照画像の使い方]` 節は本文に入れない
- scene 3 以降のように範囲が大きいときは、scene 単位で request authoring を分割してよい
  - 各担当は `script.md`、`video_manifest.md`、現在の request draft、`docs/implementation/image-prompting.md` を必ず読む
  - motion や first/last frame の判断が絡む scene では `docs/video-generation.md` も必ず読む
  - 担当 scene の `visual_beat` を semantic source にして、stateless な request 文へ書き直す
  - その出力はまず `scratch/request_rewrites/<scene>.md` に置き、担当 `p600` L2 supervisor が統合して shared request file を更新する
- scene image request の本文を組み立てるときは、`script.md` の `human_review.approved_visual_beat` を最優先し、なければ `visual_beat` を使う
- 既存の設計メモや旧 docs に `story.md` 参照が残っていても、scene image request の意味設計は `script.md` を優先する
- `p620` で request を全面改稿する時は、scene 単位で自然言語エージェントへ分割してよい
  - 各 scene subagent は `script.md` / `video_manifest.md` / 現在の `image_generation_requests.md` / `docs/implementation/image-prompting.md` を読む
  - motion や first/last frame の判断が絡む scene では `docs/video-generation.md` も読む
  - shared request file は直接編集させず、scene 単位の scratch rewrite を出させる
  - 担当 `p600` L2 supervisor がそれを統合して `image_generation_requests.md` を更新する
  - この scene 分割は image generation run ごとに再現できるよう、順番・担当範囲・統合手順を固定する
  - 採用した rewrite と理由は `subagent_trace` または review artifact に残す
- scene image prompt は「場面全体の説明」ではなく、**その動画を始める最初の1フレーム**として設計する
- したがって `太郎が話し、乙姫がうなずく` のような mid-action 完了形は弱い
- ここで重要なのは抽象的に `動き出す直前` と書くことではなく、**その場面では何が最初の1フレームに見えるべきかを具体化すること**
- ただし `最初の1フレーム` / `1フレーム目` / `first frame` は authoring / review 用のメタ情報であり、`image_generation.prompt` 本文には入れない
  - 画像生成 API へ渡す prompt は「見えている初期状態」だけを書く
  - 例: `王子が手を伸ばす直前、階段の手前にガラスの靴が大きく残っている`
  - 悪い例: `この画像は動画の最初の1フレームとして使う`
- この具体化はコードの定型変換で行わない。`script.md` の `visual_beat`、人レビュー、request review を踏まえて、自然言語エージェントが request 本文に落とし込む
- スクリプトは request 生成時に `script.md` の `human_review.approved_visual_beat` / `visual_beat` を優先して request に載せるが、最初の1フレームの意味づけ自体は自動執筆しない
- evaluator は `first_frame_readiness` を持ち、scene image prompt が first frame として妥当かを評価する
- `prompt_authoring_context` は prompt 生成エージェントと review エージェントのためだけに置ける。生成 API に送る対象ではない。

```yaml
image_generation:
  prompt_authoring_context:
    image_role: "video_first_frame_candidate"
    first_frame_question: "この動画がこの静止画から動き出すなら、冒頭で何が見えているべきか"
    api_prompt_policy: "do_not_include_authoring_context"
```

review では次を blocker とする:

- prompt 本文に `最初の1フレーム` / `1フレーム目` / `first frame` のような authoring metadata が残っている
  - canonical reason key: `prompt_contains_first_frame_metadata`
- prompt が action の途中または完了後の絵に見え、動画の冒頭静止画として不自然
  - canonical reason key: `image_prompt_not_first_frame_ready`
  - weak score key: `image_prompt_first_frame_readiness_weak`

## 言語ポリシー（重要）

- `video_manifest.md` は **日本語で書く**（修正指示・レビューを日本語で完結させるため）。
- 見出しは **日本語**で書く。review gate は `[全体 / 不変条件]`, `[登場人物]`, `[小道具 / 舞台装置]`, `[シーン]`, `[連続性]`, `[禁止]` の 6 ブロックを必須として扱う。
  - 生成スクリプト側は英語見出しも互換で認識するが、運用は日本語に寄せる。
- prompt 本文も日本語で完結させる。英語の production shorthand を混ぜない。
- 禁止語彙（`禁止` / `assets.style_guide.forbidden`）も日本語で書く方向で統一する（例: `画面内テキスト`, `字幕`, `ウォーターマーク`, `ロゴ`）。

必須ブロック（順序固定）:

1) `全体 / 不変条件`（全scene共通の不変条件）
2) `登場人物`（人物・参照一致）
3) `小道具 / 舞台装置`（重要アイテム/舞台装置の不変条件）
4) `シーン`（場面固有の描写）
5) `連続性`（前後接続）
6) `禁止`（禁止/地雷）

この 6 block は推奨ではなく required。subagent review は block の欠落を検出した時点で false にする。

この repo の生成は、最終的に `scenes[].image_generation.prompt` のテキストをそのまま API に渡すため、
**「どこに何を書くか」自体をテンプレ化**すると品質が安定する。新規の静止画は、anchor を作る scene/cut に集中させる。

---

## 0) scene contract から prompt への翻訳ルール

p600 は、p400 が作った scene/cut contract を生成 provider が描ける言葉に翻訳する stage である。
`tts_text` や narration をそのまま絵にするのではなく、scene の劇的責務を画面要素に変換する。

### 0.1 入力優先順位

1. `video_manifest.md.scenes[].cuts[].scene_contract`
2. `script.md.scenes[].cuts[].visual_beat` / `approved_visual_beat`
3. `video_manifest.md.assets.*_bible`
4. `human_change_requests[]` / `approved_image_notes[]`
5. narration / `tts_text`（補助参照のみ）

除外する入力:

- `motion_brief`: p800 motion prompt の正本。p600 image prompt authoring では読まない、prompt 本文にも要約しない。

### 0.2 変換表

| contract field | prompt への変換 |
|---|---|
| `dramatic_question` | `[シーン]` の中で、観客が何を画面から気にするかが読める配置にする |
| `value_shift.visible_evidence` | 表情、距離、手、姿勢、光の変化、壊れた/残された物などに翻訳する |
| `causal_turn` | still では「turn が起きる直前」または「turn の結果が初めて見える瞬間」として具体化する |
| `visual_thesis` | 主被写体、前景アンカー、中景の行為、背景の意味を 1 枚に圧縮する |
| `must_show` | 画像・動画・ナレーションのどこで回収するかを明確にし、画像に必要なものだけ prompt に書く |
| `must_avoid` | reveal 早出し、人物混入、場所漂流、文字要素などを `[禁止]` に書く |
| `first_frame_brief` | prompt 本文に `最初の1フレーム` と書かず、見えている初期状態だけを書く |

`motion_brief` はこの表の対象外とする。
p600 still は `first_frame_brief` だけを見て作り、motion の内容は p800 で読む。

### 0.3 映画的 still の必須要件

- **主役の優先順位**が明確である。観客が最初に何を見るかを書き分ける。
- **前景/中景/背景**がある。平面的な説明絵にしない。
- **行為の入口**がある。人物や物がすでに全てを終えている絵にしない。
- **感情の証拠**がある。顔だけでなく距離、姿勢、手、視線、光で読ませる。
- **因果の証拠**がある。次に何が起こりそうかを、道具・入口・視線・進行方向で示す。
- **reference の維持点**が明確である。path ではなく、何を同一に保つかを書く。

### 0.4 action 完了絵を避ける

弱い still:

- `王子がガラスの靴を拾い、シンデレラを見つけて微笑んでいる。`
- `浦島が箱を開け、白い煙が広がって老人になっている。`

強い still:

- `王子の手が階段の手前で止まり、片方のガラスの靴が前景に大きく残っている。奥の扉には去っていく足音の気配だけがある。`
- `浦島の手が箱の蓋の縁に触れる直前で止まり、蓋の隙間から細い白い光だけが漏れている。顔には迷いが残る。`

前者は scene の turn を still 内で完了させる。後者は p800 で動き出す余白を残す。

### 0.5 attention hierarchy block（推奨）

`[シーン]` には可能なら次の順で書く。

```text
舞台: <場所・時間・空気>。
主役: <観客が最初に見る人物/物>。
前景: <手元/小道具/境界/障害>。
中景: <人物の姿勢・距離・行為の入口>。
背景: <場所の意味・危険・誘惑・出口>。
光: <感情/reveal/時間を示す光>。
構図: <視線誘導、進行方向、空間の奥行き>。
```

### 0.6 追加 blocker

review では次を blocker とする。

- scene の `causal_turn` または `value_shift.visible_evidence` が prompt に翻訳されていない。
  - canonical reason key: `prompt_missing_scene_turn` / `prompt_lacks_visual_evidence`
- 主被写体の優先順位、前景/中景/背景が曖昧で、観客の視線が迷う。
  - canonical reason key: `prompt_lacks_attention_hierarchy`
- still が行為の完了後を描き、p800 で自然に動き出せない。
  - canonical reason key: `prompt_finishes_action_in_still`
- cut が setup / pressure / turn / payoff / reaction / handoff のどれを担当するか不明。
  - canonical reason key: `prompt_missing_cut_function`
- prompt が `motion_brief` の後続動作を先読みして、静止画に未来の出来事や完了状態を入れている。
  - canonical reason key: `prompt_leaks_motion_brief`

## 1) 画像品質を上げる prompt の原則（portable / cross-model）

### 1.1 具体に落とす（曖昧語の連打を避ける）

悪い例:
- “beautiful, epic, amazing”

良い例:
- 被写体（誰/何） + 位置関係（前景/中景/背景） + 光（どこから/色） + カメラ（POV/画角/動き）

### 1.2 一貫性は「固定フレーズ + 参照画像」で作る

人物/小物/手元が重要なら:
- **参照画像**（character / hands / props）を用意し、必要なscene/cutで `references` に入れる
- さらに **同じ語で**特徴を繰り返す（言い換え禁止）
- 参照画像は、毎回新規に作るのではなく、同じ場所/物体/人物状態をまたぐ複数scene/cutの共通アンカーとして再利用する

### 1.3 “構図のアンカー”を明示する

画像生成は「何が重要か」の優先順位に迷うと破綻しやすい。
優先したい要素は **画面内の位置**まで書く:

- “a clear foreground anchor in the lower foreground (e.g., hands+bar for an immersive ride, or a prop like a compass)”
- “leading lines centered (path / track / rail)”
- “main subject in the mid-ground”

（日本語で書くなら例）
- 「画面下の前景に“アンカー”（手元/小道具など）」
- 「導線（道/軌道/レール）を中央構図」
- 「登場人物は中景」

### 1.4 ネガティブは「禁止カテゴリ + 事故りやすい欠陥」を短く

入れすぎると逆に不安定になるので、まずは以下を定番化:
- 文字系: `画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし`
- スタイル: `アニメ/漫画/イラスト調を避ける`
- 手/人体: `手の崩れを避ける、指の増殖を避ける`

### 1.5 “シネマ/写真”語彙は「必要なものだけ」使う（チートシート）

モデルやプロバイダに依存しにくい（＝cross-modelで通りやすい）語彙だけに絞る。

- Shot / framing:
  - `導入の広いショット`, `中距離`, `クローズアップ`, `一人称POV`, `中央構図`
  - `foreground / mid-ground / background` を必ず書く（位置指定が強い）
- Lens / DOF:
  - `35mm lens`, `50mm lens`, `shallow depth of field`, `soft bokeh`
  - ただし “レンズ指定は必須ではない”。崩れるなら外す
- Lighting:
  - `soft key light`, `gentle rim light`, `golden hour`, `practical lighting`, `volumetric light (subtle)`
- Color / grade:
  - `warm tones`, `muted palette`, `high contrast (controlled)`
- Texture:
  - `subtle film grain`, `realistic textures`, `natural imperfections`

ポイント:
- “盛る”ための羅列ではなく、**破綻しやすい要素（手/バー/視点/構図）を守る**ために使う。

### 1.6 技術パラメータは “prompt ではなくフィールド” に寄せる

aspect ratio / size は `image_generation.aspect_ratio` / `image_generation.image_size` を使う。
既定の画像サイズは `1K` とし、より高解像度が必要な scene だけ個別に上書きする。
（`--ar` のような Midjourney 専用構文で書かない）

---

## 2) 推奨テンプレ（そのまま貼れる）

`image_generation.prompt: |` の中身:

```text
[全体 / 不変条件]
実写、シネマティック、実物セット感。自然な映画照明。
画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

[登場人物]
<character constraints that must stay consistent across scenes>

[小道具 / 舞台装置]
<object/setpiece constraints that must stay consistent across scenes>

[シーン]
舞台: <どこ/いつ/天候/空気>。
主役: <観客が最初に読む人物/物/場所>。
前景: <手元/小道具/境界/障害などのアンカー>。
中景: <人物の姿勢・距離・行為の入口>。
背景: <場所の意味・危険・誘惑・出口>。
光: <感情/reveal/時間を示す光>。
構図: <視線誘導、奥行き、進行方向>。

[連続性]
前と一致: <光/位置/進行方向>.
次への仕込み: <アンカー/色/方向>.

[禁止]
アニメ/漫画/イラスト調。
手の崩れ、指の増殖、読めない物体、パース破綻。
```

メモ:
- このテンプレは “文章の上手さ” ではなく **指示の網羅と優先順位**で勝つためのもの。
- sceneごとの創作要素（セット装飾など）は `SCENE` に入れ、根拠が必要な事実は story/research 側で担保する。

---

## 3) /toc-immersive-ride（cinematic_story）向け invariants（推奨セット）

注意: これは `/toc-immersive-ride --experience cinematic_story` 用の固定条件。通常の run / scene-series では前提にしない（必要なら個別に指定する）。

`全体 / 不変条件` に毎回入れる（または将来的に assets から自動注入する）:

- `実写、シネマティック、実物セット感`
- `視点（POV/三人称）を明示し、1カット内で視点ブレさせない`
- `前景/中景/遠景のアンカー（人物/アイテム/導線）を指定する`
- `画面内テキストなし、字幕なし、ウォーターマークなし`

さらに “事故りやすい” ので早めに禁止しておく:
- `アニメ/漫画/イラスト調`
- `人体の崩れ / 指の増殖 / パース破綻`

## 3.2 /toc-immersive-ride（cloud_island_walk）向け invariants（推奨セット）

`cloud_island_walk` は「雲上の島を歩いて理解を深める」体験テンプレ。
`全体 / 不変条件` の定番（scene間の一貫性のため）:

- `一人称POVで前進しながら歩く`
- `雲海の上に浮かぶ楽園の島`（概念を実写の比喩として表現）
- `水平線安定、カメラ高さ一定、道/導線を中央`（連続性アンカー）
- `実写、シネマティック、実物セット感`
- `画面内テキストなし、字幕なし、ウォーターマークなし`

特に地雷なので早めに禁止しておく:
- `アニメ/漫画/イラスト調`
- `手の崩れ / 指の増殖`
- `画面内テキスト / 字幕 / ウォーターマーク / ロゴ`
- `三人称 / 肩越し / 自撮り`

## 3.1 character_bible を scene で選ぶ（混ざり防止）

<!-- image-gen-setting:character:start -->
人物参照は `assets.character_bible` と `image_generation.character_ids` を正本にする。
人物が出る still では、顔、髪型、衣装、年齢感、体格、シルエットを固定し、参照画像に写る同一人物として読み取れるように書く。
B-roll など人物を映さない scene は `character_ids: []` を明示し、人物の混入を避ける。
<!-- image-gen-setting:character:end -->

複数キャラがいる物語では「全キャラ参照を全sceneに入れる」と混ざって破綻しやすい。
この repo では `video_manifest.md` の `image_generation.character_ids` で、そのsceneに登場するキャラだけを選び、
`--apply-asset-guides --asset-guides-character-refs scene` で参照画像/固定フレーズを注入する運用を推奨する。
人物が出る still では、`assets/characters/<name>_refstrip.png` が存在する場合、それも reference に自動で含めて一貫性を強める。
さらに `assets.character_bible[].physical_scale` と `relative_scale_rules` があれば、still prompt の `[登場人物]` に自動注入し、絶対体格と相対サイズを固定する。
`assets.character_bible[].review_aliases` があれば、story/script review で「その cut に本来出るべき人物が prompt/character_ids から欠けていないか」を検査できる。

B-roll（キャラを映さない）sceneは `character_ids: []` を明示し、キャラ注入ゼロにする。

- `character_reference` scene は reference-only として扱い、**全身（頭からつま先まで）** だけを撮る
- 顔寄り、上半身のみ、途中クロップの基準画像は作らない
- 参照用の識別子は人間が読める安定名にする（例: `protagonist_front_ref`, `protagonist_side_ref`, `protagonist_back_ref`）

### Human character baseline（推奨）

人間キャラは、物語上の特段の理由がない限り「美男美女（映画俳優レベル）」を初期値にする。
`assets.character_bible[].fixed_prompts` に短文で入れて固定する（例）:

- `人間キャラは美男美女（映画俳優レベル）。顔立ちのバランス、肌の質感、表情、目の印象が自然で実写的`

注意:
- “魅力”は過度な誇張より、実写で成立する自然さ（骨格/肌/表情/所作）を優先する

## 3.3 object_bible を scene で参照する（舞台装置の映画品質）

この repo では、竜宮城/玉手箱のような「背景ではなく物語の主役級 setpiece / artifact」を
`assets.object_bible` として設計し、scene 側は `image_generation.object_ids` で参照する運用を推奨する。

- 目的: “本や絵本では語られなかったディテール”を、**映像だけで伝わる情報**として固定し、sceneの思いつきにしない
- 運用:
  - `assets.object_bible[].reference_images` を先に生成（`assets/objects/...png` を `image_generation.output` にする reference scene）
  - story scene は `object_ids: ["..."]` を宣言
- 生成は `--apply-asset-guides` で、object の固定フレーズを `小道具 / 舞台装置` に自動注入する
  - 見出しは日本語推奨（`[小道具 / 舞台装置]`）。スクリプト側は英語見出しも互換で認識する。

ポイント:
- 画面内の文字で説明しない（看板/刻印/銘板などは禁止）。**形/光/動き/ショー性**で理解させる。
- “物語に直接関係しない”ショー/仕掛けでも、映像の魅力と世界の深みを作る（spectacle）。

### 3.4 Ryugu exploratory block（Otohime 登場前の視覚報酬）

`ryugu_palace` の内部を見せる場面では、乙姫をすぐに登場させず、まず **4-6 cuts / 1 cut = 約4秒** の探索ブロックとして設計してよい。

このブロックの目的は次の通り。

- 竜宮城を「説明」ではなく「発見」で見せる。
- 実写の見せ物として、建築・機構・光・群泳を先に印象づける。
- 乙姫の登場を遅らせ、次のドラマの入口を強くする。

推奨ルール:

- `character_ids: []` を基本にし、乙姫は出さない。
- `object_ids: ["ryugu_palace"]` を使い、舞台装置を固定する。
- 各 cut は `4` 秒前後、ナレーションなし。
- 最後の cut は「乙姫が現れる直前の門/回廊/玉座の間の入口」で止める。

竜宮城探索ブロックの prompt には、以下の順で書くと安定しやすい。

1. `[全体 / 不変条件]` に実写・映画照明・実物セット感を明記する。
2. `[登場人物]` には `人物なし。乙姫も背景人物も入れない` と書く。
3. `[小道具 / 舞台装置]` に `ryugu_palace` の固定フレーズを入れる。
4. `[シーン]` で門 / 回廊 / 吹き抜け / 光の仕掛け / threshold を cut ごとに変える。
5. `[連続性]` では、この画像だけで何が読み取れるべきかを書く。前後の cut を前提にした記述は request 本文に入れない。
6. `[禁止]` に文字要素とアニメ調を再掲する。

例:

```text
[全体 / 不変条件]
実写映画調、自然な映画照明、実物セット感。水中の光は幻想的だが、素材は珊瑚・真珠層・濡れた金属として実在感を持たせる。画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

[登場人物]
人物なし。乙姫も背景人物も入れない。

[小道具 / 舞台装置]
竜宮城は生きた珊瑚、真珠層、漆を塗った青銅の骨組みでできている。表面は濡れた艶を持ち、実写の巨大建築として縮尺が分かる。
内部には泡の灯籠、発光する珊瑚のシャンデリア、ゆっくり制御された潮流、遠くを回る魚群がある。看板、刻印、銘板はない。

[シーン]
舞台: 竜宮城の入口回廊。
主役: 半分開いた珊瑚門と、その奥に続く発光する回廊。
前景: 濡れた珊瑚の床と、ゆっくり上がる小さな泡。
中景: 門の骨組みが左右から画面を囲み、観客の視線を奥へ導く。
背景: 遠くの吹き抜けで魚群が渦を作り、宮殿そのものが呼吸しているように見える。
光: 上方から揺れる水面光、奥から淡い金色の反射。
構図: 縦型9:16、門を前景フレームにし、回廊の奥行きを中央に置く。

[連続性]
この画像だけで、招かれた者だけが入れる別世界の入口だと読める。乙姫はまだ現れず、次に奥へ進める余白を残す。

[禁止]
乙姫、人物、画面内テキスト、字幕、看板、銘板、ウォーターマーク、ロゴ、アニメ調、漫画調、イラスト調、読めない形、平面的な水族館背景。
```

manifest 断片例:

```yaml
scenes:
  - scene_id: 50
    cuts:
      - cut_id: 1
        cut_role: "visual_payoff"
        scene_contract:
          cut_function: "setup"
          target_beat: "竜宮城を説明ではなく発見として見せる"
          first_frame_brief: "人物なし。半分開いた珊瑚門の奥に発光する回廊が見える"
          motion_brief: "p800 専用。カメラがゆっくり門の奥へ進み、泡と魚群だけが動く"
        image_generation:
          character_ids: []
          object_ids: ["ryugu_palace"]
          location_ids: ["ryugu_palace_corridor"]
```

## 4) 具体例（cinematic story）

### 4.1 Character turnaround 基準画像（scene_id: 0, full-body only）

この repo では、キャラクター参照画像を「前/横/後ろ」の3枚で作り、さらに3枚を横並び結合した1枚（動画生成側の参照）も作る運用を推奨する。
`scripts/generate-assets-from-manifest.py` の `--character-reference-views front,side,back --character-reference-strip` で自動生成できる。

また、後から中間sceneを差し込めるように `scene_id` は **10刻み**（例: 10,20,30...）で運用するのがおすすめ（後段は scene_id の連番を前提にしない）。
`scene_id: 0` は character_reference 専用に分け、story scene の spacing と混ぜない。

```text
[全体 / 不変条件]
実写映画調、自然な映画照明、人物参照用の清潔な背景。画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。

[登場人物]
主人公の全身参照。頭からつま先まで全身が見える。顔、髪型、年齢感、体格、衣装の形と素材が後続sceneで再利用できるように明瞭。

[小道具 / 舞台装置]
主役級の小道具は持たせない。衣装と身体シルエットの確認を優先する。

[シーン]
舞台: 参照画像用のニュートラルな室内。
主役: 人物の全身。
前景: なし。足先まで隠さない。
中景: 人物が直立し、自然な姿勢で立つ。
背景: 余計な装飾のない薄い背景。
光: 柔らかなキーライトと弱いリムライト。
構図: 縦型、全身が切れない中央構図。

[連続性]
この画像だけで、後続sceneが参照すべき顔、髪型、体格、衣装、足元までのシルエットが分かる。

[禁止]
顔寄り、上半身だけ、足先のクロップ、アニメ調、漫画調、イラスト調、過度なメイク、画面内テキスト、ウォーターマーク。
```

### 4.2 Scene 1（世界への入口）

```text
[全体 / 不変条件]
実写映画調、自然な映画照明、実物セット感。画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。視点は客観三人称で固定。

[登場人物]
物語キャラクターが映る場合は character_bible の参照画像と同じ顔、髪型、衣装、年齢感を維持する。人物が映らない場合は人物なしと明示する。

[小道具 / 舞台装置]
入口の門、濡れた石畳、奥へ続く光の筋を場所アンカーとして扱う。看板や刻印で説明しない。

[シーン]
舞台: 夕暮れの霧がかかった異世界の入口。
主役: 半分だけ開いた大きな門。観客はその奥に何があるかを気にする。
前景: 濡れた石畳と低い霧。画面下から門へ向かう導線を作る。
中景: 門の隙間に立つ人物、または人物なしの場合は門の影。
背景: 門の奥から漏れる暖かい光と、まだ見えない世界の輪郭。
光: 外側は青灰色、門の内側だけ暖色。
構図: 縦型9:16、門を中央に置き、道の線で視線を奥へ導く。

[連続性]
この画像だけで、日常の外側から未知の世界へ入る直前だと読める。次cutでは門の奥へ進める余白を残す。

[禁止]
アニメ調、漫画調、イラスト調、CGIだけに見える質感、歪んだ手、余計な指、画面内テキスト、ロゴ。
```

### 4.3 Scene 2（最初の見せ場へ）

```text
[全体 / 不変条件]
実写映画調、自然な映画照明、実物セット感。画面内テキストなし、字幕なし、ウォーターマークなし、ロゴなし。カメラ高さは安定。

[登場人物]
登場人物が映る場合は参照画像と同じ人物。顔、髪型、衣装、体格を維持する。見せ場の対象が主役の場合、人物は中景または端に控えめに置く。

[小道具 / 舞台装置]
scene の主役級 setpiece を object_bible と一致させる。材質、構造、光、縮尺感を維持し、文字で説明しない。

[シーン]
舞台: <topic> の世界の新エリアへ入った直後。霧、水しぶき、濡れた金属反射がある。
主役: 最初の大きな見せ場が奥に現れる。まだ全貌は見せ切らず、観客が近づきたくなる状態。
前景: 控えめな霧と水滴。視界を邪魔しない。
中景: 必要なら物語キャラクターの背中や横顔。視線は見せ場へ向く。
背景: 見せ場の対象が画面奥を支配する。
光: 前sceneと光源方向/色温度をつなぎつつ、奥から強い反射光が出る。
構図: 奥行きを強調し、次cutで寄れるよう主役対象を中央奥に置く。

[連続性]
前sceneの光源方向と空気感を保つ。この画像だけで、次cutが見せ場へ寄っていくことが分かる。

[禁止]
アニメ調、漫画調、イラスト調、読めない形、極端なモーションブラー、画面内テキスト、ウォーターマーク。
```

---
## 5) チェックリスト（生成前レビュー）

- [ ] 視点（POV/三人称）とカメラ意図が明示されている（1カット内でブレない）
- [ ] “画面内のアンカー”が書かれている（前景/中景/背景の配置。手元固定に限らない）
- [ ] 観客が最初に見る主被写体の優先順位が明確である
- [ ] `scene_contract.value_shift.visible_evidence` が画面要素へ翻訳されている
- [ ] `causal_turn` が、起きる直前または結果が初めて読める状態として具体化されている
- [ ] still が action 完了絵になっておらず、p800 で自然に動き出せる余白がある
- [ ] `motion_brief` を画像 prompt の入力に使っていない。後続動作や未来の出来事を prompt 本文に書いていない
- [ ] 参照画像を使う前提の文がある。path ではなく、何を一致させるかを書いている
- [ ] 禁止事項（文字/アニメ調/崩れ手）が短く入っている
- [ ] scene固有の差分（場所/時間/出来事）が 1〜3文で具体
- [ ] continuity が1行でも入っている（この画像だけで読み取れる状態の明記）
- [ ] prompt 本文に `scene_id` / `cut_id` / `最初の1フレーム` / 作品タイトルだけの説明が残っていない

---

## 6) Sources（調査メモ）

※ 本ドキュメントは以下の prompt guide / 公式ドキュメントの考え方をベースに、repoの manifest 契約に合わせて整理した。

- Google Cloud Vertex AI: Prompt and image attribute guide（Imagen / 画像生成の prompt の書き方）
  - https://cloud.google.com/vertex-ai/generative-ai/docs/image/img-gen-prompt-guide
- Google Cloud Vertex AI: Generate and edit images with Gemini（Gemini 画像生成の利用方法/制約）
  - https://cloud.google.com/vertex-ai/generative-ai/docs/image/generate-images
- Google Cloud Vertex AI: Subject reference / customization（参照画像を使った一貫性の考え方）
  - https://cloud.google.com/vertex-ai/generative-ai/docs/image/subject-customization
- Gemini API reference（ImageConfig: aspectRatio / imageSize など）
  - https://ai.google.dev/api/caching#imageconfig

## Judgment Review Helper

画像 prompt の `hard function checks` とは別に、contextless subagent へ判断レビューを依頼したい場合は [docs/implementation/image-prompt-judgment-review.md](/Users/kantaro/Downloads/toc/docs/implementation/image-prompt-judgment-review.md) を参照する。

関連 helper:

- `python scripts/build-image-prompt-judgment-review.py --run-dir output/<topic>_<timestamp> [--manifest <path>] [--mode generate_still]`

この helper は `logs/review/` 配下に frozen review collection、review scope、subagent prompt、judgment template を作る。manifest への writeback は行わず、subagent の判断を run-local artifact として別管理する。

## Cut First-Frame Authoring v2.1

p600 は `cut_contract.first_frame_contract` を 6 block prompt へ翻訳する stage である。既存の `scene_contract` は互換 alias として扱えるが、cut 単位の正本は `cut_contract` とする。

入力優先順位:

1. `cut_contract.first_frame_contract.first_frame_brief`
2. `cut_contract.viewer_contract.visual_proof`
3. `cut_contract.cinematic_contract.subject_priority`
4. `cut_contract.cinematic_contract.screen_geography`
5. `cut_contract.continuity_contract`
6. asset / character / object / location bible
7. narration は補助参照のみ

`motion_contract.motion_brief` は p600 では読まない。prompt 本文にも要約しない。

`action_completion_state` は、still がどの時点の画かを固定する。`pre_action` は threshold / reveal 直前、`early_action` は行為開始直後、`mid_action` は途中状態、`aftermath` は reaction / handoff、`hold` は余韻や沈黙に使う。

追加 reason key:

```yaml
- prompt_missing_cut_contract
- prompt_missing_visual_proof
- prompt_missing_screen_geography
- prompt_missing_action_completion_state
- prompt_finishes_cut_action
- prompt_reads_motion_contract
- prompt_reveals_next_cut_information
```
