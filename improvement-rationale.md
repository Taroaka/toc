# 改善理由・設計判断メモ

## 目的

前段で作られる台本から、映画のレベルで機能する scene 群を作るために、scene関連ドキュメントとテンプレートを改善した。
今回の改善の中心は、scene を「時間で切った説明単位」から「観客の理解・感情・期待を変化させる劇的単位」へ引き上げること。

## 既存ファイルで見つかった主な課題

1. **scene の劇的責務が弱い**
   - 既存の `scene_intent` は story_purpose / audience_information / affect_transition を持っていたが、scene 内で何が変化するか、何が次 scene を発生させるかが必須ではなかった。
   - そのため、きれいな scene は作れても「物語が進む scene」にならないリスクがあった。

2. **cut 分割が尺と説明都合に寄りやすい**
   - 既存にも cut 数ルールはあったが、各 cut が setup / pressure / turn / payoff / reaction / handoff のどれを担うかが明示されていなかった。
   - そのため、重要な reveal や感情反転が 1 cut に圧縮されるリスクがあった。

3. **p400 と p600 の責務境界が一部あいまい**
   - `docs/script-creation.md` の古いテンプレには `generation_prompt` があり、p400 で完成 prompt を書いてしまう流れが残っていた。
   - 改善版では p400 は `first_frame_brief` / `visual_beat` / `p600_image_handoff` までにし、完成 prompt は p600 で作るように整理した。

4. **image prompt が場面説明になりやすい**
   - 既存ルールは6ブロック構造を定義していたが、scene の value shift や causal turn を画面証拠へ翻訳するルールが弱かった。
   - 改善版では `scene_contract` から prompt への変換表、attention hierarchy、action完了絵を避けるルールを追加した。

5. **テンプレート内の必須ブロック不整合**
   - `workflow/video-manifest-template.md` のサンプル prompt は、必須とされる `[登場人物]` / `[小道具 / 舞台装置]` / `[連続性]` が欠けていた。
   - `workflow/scene-video-manifest-template.md` の cut1 prompt も `[小道具 / 舞台装置]` が欠けていた。
   - 改善版では全テンプレートの prompt を6ブロック必須に揃えた。

## 追加した中心概念

### Dramatic Question

各 scene の間、観客が追う問い。
例: `主人公は真実を見つけるのか`、`浦島は誘惑に飲み込まれるのか`。
問いがない scene は説明や素材集になりやすいため、p410 gate の必須項目にした。

### Value Shift

scene の前後で変わる価値・感情・関係。
例: `安心 → 不安`、`無知 → 理解`、`孤立 → 接続`。
変化は `visible_evidence` として、画面で読める証拠まで書くようにした。

### Causal Turn

次 scene を発生させる不可逆の出来事・決断・発見。
これがない scene は、物語全体の因果から外れやすい。

### Visual Thesis

その scene を代表する映画的な一枚絵。
単なる「美しい背景」ではなく、scene の意味が画面から読める構図の考え方。

### Cut Function

各 cut の劇的役割。
`setup|pressure|threshold|turn|payoff|reaction|handoff` を追加し、重要sceneが1 cutに圧縮されるのを防ぐ。

### First Frame Brief / Motion Brief

p600 still と p800 motion の接続を安定させるために追加した。
静止画は「行為の完了後」ではなく「動画が動き出す直前の状態」として設計し、motion prompt はその still から自然に始まる動きに限定する。

## ファイル別の主な改善

### `scene-prompt-files-summary.md`

- scene の意義を再定義した。
- 読む順番を、p400 scene contract → p420 cut blueprint → p600 still prompt → p800 motion の順に整理した。
- 最小契約とNGパターンを追加した。

### `docs/script-creation.md`

- `p400 Cinematic Scene Design Contract` を追加した。
- `scene_intent` に dramatic_question / scene_spine / value_shift / causal_turn / visual_thesis / spatial_plan / coverage_review を追加した。
- `cut_blueprint` に cut_function / screen_question / first_frame_brief / motion_brief を追加した。
- p400 の古い `generation_prompt` を `p600_image_handoff` に置き換えた。

### `docs/implementation/scene-loop.md`

- scene-set review、scene detail review、scene cinematic gate を明確化した。
- p410 blocking findings を追加した。
- cut review の観点を、劇的役割・first frame・motion まで拡張した。

### `docs/implementation/image-prompting.md`

- scene contract から prompt への翻訳ルールを追加した。
- attention hierarchy と action完了絵を避けるルールを追加した。
- `prompt_missing_scene_turn` などの reason key を追加した。
- 生成前チェックリストを映画的 scene prompt 向けに拡張した。

### `docs/video-generation.md`

- still → motion → clip の接続原則を追加した。
- `cut_function` に応じた motion prompt の役割を定義した。
- p600 still と p800 motion の矛盾を gate で戻す方針を追加した。

### `docs/implementation/asset-bibles.md`

- asset を scene の劇的装置として扱う考え方を追加した。
- scene から asset を逆算する基準、asset化しない基準、staged reveal を追加した。

### `workflow/scene-outline-template.yaml`

- scene contract と cut blueprint を直接持つテンプレートへ刷新した。
- research grounding、creative invention、visual_world、handoff_notes を分離した。

### `workflow/scene-conte-template.md`

- scene contract、beat ladder、cut card、manifest落とし込みチェックを追加した。
- 3〜5 cut の単純ルールから、scene の劇的流れに基づく cut 分解へ変更した。

### `workflow/scene-script-template.md`

- Q&A中心の短尺テンプレから、cinematic scene script として使える構造へ変更した。
- scene_intent、narration_plan、cuts、quality_check を追加した。

### `workflow/scene-video-manifest-template.md`

- scene単体 run でも cinematic scene contract を保持するよう刷新した。
- prompt を6ブロック必須に統一した。
- image review、still_image_plan、motion prompt の最小構造を追加した。

### `workflow/video-manifest-template.md`

- `scene_intent` と `scene_contract` を拡張した。
- サンプル image prompt を6ブロック必須かつ映画的 still として成立する形へ修正した。
- image_generation の `contract` / `review` field を実体として追加した。

## 運用時の推奨

1. p400 では、まず scene ごとに `dramatic_question`、`value_shift`、`causal_turn` を埋める。
2. scene-set review で、scene の追加/削除/統合/順序を確認する。
3. per-scene review で、各 scene が説明ではなく出来事になっているか確認する。
4. p420 で cut を `setup|pressure|threshold|turn|payoff|reaction|handoff` に分ける。
5. p500 で、scene の turn / payoff / continuity に必要な asset を固定する。
6. p600 で、`first_frame_brief` を6ブロック prompt に翻訳する。
7. p800 で、motion prompt が still から自然に始まり、cut_function を実行しているか確認する。

## 注意点

- 今回はドキュメントとテンプレートの改善であり、実行スクリプト自体は変更していない。
- 新 field を使う場合、既存の検証スクリプトが未知 field を許容するか確認が必要。
- 既存の run に適用する場合は、まず `scene_outline` と skeleton `video_manifest` を再生成し、その後 p500/p600 へ進むのが安全。
