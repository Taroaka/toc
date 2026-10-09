# 実装順・検証計画

状態: 2026-09-19にユーザーが実装開始を依頼。コード・契約・ガイドの修正を実施。検証結果は [validation.md](validation.md)。
最初の完成単位は、新規runが原作の意味を定型文で変更せずp450へ到達すること。
単にp300文書を短くして、下流が壊れた状態で止めない。

## 0. 変更前の挙動を固定する

- [x] `tests/` に制作結果の違いを検査する少数のfixtureを用意する。下表のケースを使う。
- [x] E2〜E7の値が、どの新規経路のartifact/author入力へ入るかを実際の出力で確認する。
- [x] p400のフィールドを、参照整合性に必要なもの、作品次第のauthoring判断、既存互換に分類する。
- [x] 既存v1とmarkerなしlegacyの正常な入力・再開fixtureを保存する。
- [x] 現在の上流source-first実装のテストを確認し、既存のユーザー変更を保持する。

成果物: 再現可能な入力、現在の出力、失われる/追加される情報、該当関数の短い記録。
品質スコアではなく、変更前後で比較できる事実を残す。

## 1. p300とp400を一緒に切り替える — 最優先

- [x] 9月17日のp300設計を再利用し、共通authoringとv2 validatorを実装する。
- [x] frontendの `visual = {...}` を共通入口へ置換。全編の固定価値、配色、番号由来のvalue割当を除く。
- [x] story本文、実在scene ID、source bindingをauthor入力に渡す。入力の黙示的truncateをしない。
- [x] 新規v2のp400では定型blueprintを初期値にしない。作者のscene/event/stateを直接利用する。
- [x] dramatic question、不可逆なturn、相反感情、iconic moment、全演出領域の一律必須を見直す。
- [x] `start/end_state` が同じ場合や、演出notes空の場合を正常に扱う。scene欠落やruntime failureとは分ける。
- [x] script/manifest/source ledger/cut contextの参照・digest・版を一方向に揃える。
- [x] writer/reader/validator/template/docsを同じ変更単位で同期し、p450までの統合テストを通す。

主な対象:

- 新規候補: `toc/visual_value_authoring.py`、`scripts/author-visual-value-with-codex.py`
- `scripts/toc-immersive-frontend-run.py`
- `toc/adaptation_value_contract.py`、`toc/stage_evaluation/research_story.py`、`toc/stage_evaluation/pipeline.py`
- `toc/scene_acceptance_contract.py`、`toc/cut_context_packet.py` の該当reader
- `workflow/visual-value-template.yaml`、script/cut/manifestテンプレート、stage-grounding
- data-contracts、story-creation、script-creation、adaptation-value-amplification、agent rolesの該当節

## 2. p100/p200の判断指針と実際の入力を揃える

- [x] 既存 `AUDIENCE_MEANING_INSTRUCTION` に必要な差分だけを加え、同義の巨大な別指示を作らない。
- [x] 原作の事実、人物の自己説明、他者の評価、creative additionの帰属が下流へ残ることを確認する。
- [x] 成功と代償、外的成果と内的悪化、集団ごとの評価を保持するfixtureを追加する。
- [x] 原作の因果と、sceneの配置理由を混同しない。支持されない因果を補完する経路を確認する。
- [x] 新作向けの発想と、既存原作の映像化の指示を分ける。全人物に傷や改心を要求しない。

主な対象: `toc/research_author.py`、`toc/story_authoring.py`、`toc/story_author_pipeline.py`、
research/storyのガイドとテンプレート。現在のlossless source inputを維持する。

## 3. p700の矛盾と過剰説明を修正する

- [x] 未回収の問いを一律禁止するpromptと、`intentional_unresolved` の既存契約を一致させる。
- [x] narratorの知識境界、人物の自己説明、観客に見せる情報がprojectionで混ざらないか確認する。
- [x] 元の映像にない心理・恒久的な変容・和解を語りで追加しない例を用意する。
- [x] silent、human_locked、通し原稿→span→cut→TTS textの既存同期を維持する。

主な対象: `scripts/ai/toc-immersive-narration-multiagent.py`、
`toc/narration_prompt_projection_registry.py`、`toc/narration_arc.py`、`toc/script_narration.py`。
既存機能がある部分は新schemaを増やさず、入力・指示・検証の整合を直す。

## 4. 素材・画像・動画への具体化を確認する

- [x] p500の固定の時間制限の光を除き、source/scriptで使われる具体的な対象だけを計画する。
- [x] 比喩/themeからobjectへの自動追加を、入口からasset計画まで通して検証する。
- [x] 同一性と状態差分を分け、first-frameの時点・所有・位置・開閉状態を守る。
- [x] 動画compilerの動作fallback到達条件を確認し、人物不在と意図的な静止のケースを扱う。
- [x] narrationとPOVの指定を混同せず、ユーザー指定の体験形式を保持する。

主な対象: frontendのasset生成部分、`toc/asset_prompt_compiler.py`、
`toc/image_prompt_compiler.py`、`toc/video_prompt_compiler.py`、対応するprojection registry。

## 5. 互換性と実際の出力を検証する

- [x] 新規v2、既存v1、markerなしlegacy、未知版、混在、stale入力を区別する。
- [x] p400 rebuildとp500 resumeが、保存対象の入力を勝手に再執筆しないことを確認する。
- [x] providerなしの統合テストと、fixtureのstory/script/manifest/promptの具体的な差を確認する。
- [x] 原作→story→visual→script→promptの保持と変換をfixtureで確認し、改善箇所を説明する。
- [ ] 実モデルによる執筆・映像/音声生成後の作品比較。今回の自動テストは生成品質を確認していない。
- [x] 既存のrender/file/provenance検証を通す。制作ごとのcritic・採点gateは追加しない。

既存runでの有料再生成や新規書籍の取得は、計画作成や単体回帰テストの前提にしない。

## 受入ケース

| ケース | 自動で確認すること | 開発時に読み比べること |
| --- | --- | --- |
| 静かな食事、原作は感情を確定しない | notes空、状態維持、source/reveal/scene対応が通る | 勝手に和解・涙・反転を足していないか |
| 職務上の成功と関係上の損失が共存 | 両方のsource eventとauthor入力が残る | 成功＝成長へまとめていないか |
| 本人は誠実に説明するが行動とずれる | 発言の帰属と観察事実のsourceが別に追える | 意図的な嘘・悪意へ書き換えていないか |
| 関心の薄い意見の不一致 | 指定しない葛藤欄を定型で補完しない | 全人格の危機へ誇張していないか |
| 比喩としての「壁」、物理的な壁はない | theme/motifがasset一覧へ増えない | 元の比喩の働きを他の表現で保持できるか |
| 意図的に未解決の結末 | existing unresolved enum、selector、span順序が通る | 教訓・解決・恒久的変容を語りで加えていないか |
| 同じ対象の受け渡し・開閉 | first-frame、motion開始/終了、所有・対象参照が一致 | 行為の原因と結果が読めるか |
| 同じ場所を二人が異なって見る | location identityと各sceneのsource対応が一致 | 主観を場所の客観的性質にしていないか |
| 一人称の語り、外から人物を見る画 | 語りとcameraの入力が独立して保たれる | 作品に合う視点の距離があるか |
| 人物不在・主動作なし | 非人物へ呼吸等のfallbackが流れない | 空間の観察として成立するか |
| 同題名・違う出来事、ID非連番 | 本文とIDで対応し、位置・題名だけで決めない | 二作品の出力が同じ定型になっていないか |
| 失敗・混在・古いsource | typed error、未完了state、再試行境界が正しい | エラーを内容不良の判定として報告していないか |

自動テストは、既知fixtureのsource/value/投影を確認する。任意の作品の感情や忠実さを一般に判定できるとはしない。
LLMのstubテストが通っても、実際のauthorの品質を検証したことにはならない。

## 利用する既存チェック

変更した領域ごとに絞って実行する。以下を無条件に毎回すべて回すという意味ではない。

- 上流: `test_source_first_research.py`、`test_research_author.py`、`test_story_authoring.py`、`test_story_author_pipeline.py`
- p300/p400: `test_adaptation_value_contract.py`、`test_stage_evaluator_scripts.py`、`test_stage_evaluator_parity.py`、
  `test_scene_acceptance_frontend_integration.py`、`test_story_neutral_production_code.py`、`test_cut_context_packet.py`
- 音声: `test_narration_prompt_projection_registry.py`、`test_narration_arc.py`、`test_immersive_narration_multiagent.py`、
  `test_silent_narration.py`、`test_narration_revision.py`
- 媒体: `test_asset_prompt_compiler.py`、`test_image_prompt_compiler.py`、`test_video_prompt_compiler.py`、
  `test_video_prompt_frontend_materialization.py`
- 再開/出力: `test_p400_rebuild.py`、`test_p500_resume.py`、`test_render_video.py` と該当provenanceテスト
- slot/readsetに触れた場合: `python scripts/validate-slot-contract.py` と、fixture runへの該当範囲のverify-pipeline

新しい固有名詞の禁止リストやprompt全文snapshotだけで、意味の保持を検証したことにしない。
既存の固有名詞混入テストは残し、出力とsourceの対応を検査するケースを追加する。

## 運用上の注意

作業ツリーには既にresearch/story/frontend/testsを含む多数の変更がある。
実装開始時は再度現在値を確認し、既存変更を巻き戻さない。
docsを編集するときはローカルガイドを読み、ルートAGENTS/CLAUDEは今回の改善対象にしない。
本計画ではモデル変更・subagent起動・自動化作成を前提としない。
