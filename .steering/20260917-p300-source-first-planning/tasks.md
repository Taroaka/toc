# p300改修：実装手順と検証

状態: 設計完了。下記の実装・テストは未実施。

## 今回の成果物

- [x] 現行p300生成、必須キー、p400全文投影、source ledger、再開境界を確認。
- [x] 必要要素、空の正常系、創作の自由、上流保護を [requirements.md](requirements.md) に定義。
- [x] 最小データ構造、authoring、consumer、互換性を [design.md](design.md) に定義。
- [x] 実装順と受入ケースを定義。

## 実装順

### 1. 契約と仕様を揃える

- [ ] `docs/data-contracts.md` にp300 v2の正式要件・done条件・版分岐を集約。
- [ ] `docs/story-creation.md`、`docs/adaptation-value-amplification.md`、
  `docs/implementation/agent-roles-and-prompts.md` を更新。必須の相反感情・象徴・5領域を外す。
- [ ] `workflow/visual-value-template.yaml` をv2の最小構造にする。
  実例はテンプレートのデフォルトにせず、ドキュメントの例として分離する。
- [ ] `workflow/stage-grounding.yaml` のvisual_value readsetとscriptへの入力を整理。
  v2ではvisual_valueを必須入力とし、legacyフローのoptional扱いを明示的に区別する。
- [ ] v1 fixtureを確保し、新規v2 fixtureを静かな場面・具体的判断ありの両方で追加する。

### 2. 最小contractとvalidatorを実装

- [ ] `toc/visual_value_authoring.py` に入力構築・scene対応・v2検証を実装する。
  pureなcontract部分とtransport呼出しを分離し、providerなしで検証できるようにする。
- [ ] `toc/stage_evaluation/research_story.py` にv2分岐を追加。notes空とscene未出力を区別する。
- [ ] `toc/adaptation_value_contract.py` と `toc/stage_evaluation/pipeline.py` の版dispatchを追加。
  v1を維持し、v2で旧欄を要求せず、原作参照の検証は残す。

### 3. p300 authoringを接続

- [ ] 既存runtimeを利用する `scripts/author-visual-value-with-codex.py` を追加。
- [ ] frontendで `visual = {...}` を共通authoring呼出しへ置換。
  固定の全編方針・scene amplification・配色・光・アンカー・handoffの生成をv2から除外。
- [ ] 入力bytes/digest、readset、author応答、構造エラーを既存ログ・ロック・stateの規則で記録。
- [ ] CLI/scaffold/assistantの各入口を同じテンプレート・validatorへ接続。
  scaffoldとauthor完了を分ける。

### 4. 下流で旧形式を復活させない

- [ ] frontendの `_scene_intent_for_cut_design`、`_cut_expressive_contract_for_scaffold` 呼出し、
  `_scene_acceptance_source_ledger` とmanifest組立をv2へ対応させる。
- [ ] source_story_scene_id、source_visual_value、visual_notesをsource ledgerとscript/manifestへ渡す。
  hash/preflightにも新しい参照を反映し、単にvalidatorを緩めて通さない。
- [ ] `workflow/script-template.yaml`、`workflow/cut-blueprint-template.yaml`、
  `workflow/video-manifest-template.md` と `docs/script-creation.md` のp300依存欄を同期。
- [ ] p500素材計画の入力にcontinuity_notesを渡す。無条件の象徴物・参照画像追加をしない。
  p600/p700も関連notesをreadsetから利用できることを確認する。
- [ ] `toc/p400_rebuild.py`、`toc/p500_resume.py` の保存・stale検出と新旧readerの整合性を確認。
  既存runを自動書換えしない。

### 5. 必要な検証で完了する

- [ ] 下表のcontract/author/runtime/引き継ぎテストを追加して実行する。
- [ ] 既存 `tests/test_adaptation_value_contract.py`、`tests/test_stage_evaluator_scripts.py`、
  `tests/test_stage_evaluator_parity.py`、`tests/test_story_neutral_production_code.py`、
  `tests/test_scene_acceptance_frontend_integration.py`、関連frontend/rebuild/resumeテストを実行する。
- [ ] `python scripts/validate-slot-contract.py` でp310/p330の整合性を確認する。
- [ ] providerをstubにしたp300→p450の統合テストで、実際に使われる入力を確認する。
- [ ] fixtureを使った出力例を開発時に読み比べ、説明だけが具体化して事実が欠落していないか確認する。
  毎回のproduction criticや採点工程にはしない。

## 受入ケース

| ケース | 期待結果 | 検証方法 |
| --- | --- | --- |
| 全sceneのnotesが空 | 正常。反転・葛藤・象徴・演出5領域を追加しない | contract + p400入力の統合テスト |
| 一sceneだけ具体的な判断あり | そのsceneへのメモが保持され、他sceneへ水増しされない | 投影・source ledger検証 |
| 場面間で同じ物を識別する必要がある | 実在sourceとsceneに結びついたcontinuityをp500が受け取る | readset/素材計画の入力テスト |
| sceneタイトルが同じで出来事が違う | author入力には両方の本文が区別して渡る | 入力構築テスト。出力の違いは開発時に比較 |
| 悲劇・未解決の結末・喜劇 | p300コードは救済・解放・時間圧力を挿入しない | 固定fallback非到達のテスト + 例比較 |
| 壮観が作品の見せ場 | 具体的な演出をnotesに保持できる | 有効な自由記述fixture |
| ナレーションが必要 | 無言・画だけで証明する義務を追加しない | 語りとの分担fixture/入力確認 |
| 欠けたscene・余分なscene・重複・順序違い | 通常の構造エラー | negative tests |
| 未解決pointer・source差替え | 通常の参照/staleエラー | negative tests |
| author応答失敗・未完 | p300 doneにせず、notes空での自動救済なし | runtime failure test |
| 非連番・文字列scene ID | 位置による誤対応なし。runtime IDと明示対応 | マッピングテスト |
| v2と旧amplificationの混在・未知版 | 明示エラー | 版分岐テスト |
| v1/markerなしの既存run再開 | 対応する既存readerで継続、ファイルの無断更新なし | 既存fixture・再開回帰テスト |
| v2 p300をv1 p400へ接続 | 生成前にstale/非互換として停止 | 境界テスト |

## 実装時の注意

作業ツリーには、この設計以前からresearch/story/frontend/testsの未コミット変更がある。
それらを正とした差分を作り、revertや過去版への丸ごと置換をしない。

この設計の変更対象に同名ファイルが含まれていても、今回追加したのは本ディレクトリ内の
設計書のみである。既存run移行や有料メディア生成はこのタスクリストの実行条件にしない。
