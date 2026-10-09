# 読書から得た改善案 — 実装・検証記録

2026-09-19。ユーザーの「計画を保存し、順番に修正する」という依頼に基づく。
計画の入口は `docs/reading/the-science-of-storytelling/improvement-plan.md`。
書籍の科学的主張の実証ではなく、ToCの入力保持・変換処理の改善を記録する。

## 実装したこと

| 工程 | 変更 | 確認した出力・入力 |
| --- | --- | --- |
| p300 | 共通authorにresearch/story全文と正本ガイドを渡す。固定の価値説明・配色・時間制限を生成する辞書を置換 | prompt内の全文、実在scene ID、空を許すnotes、runtimeが付けるraw-byte digest |
| p300検証 | `source_first_v2`、全sceneの順序、参照、source bindingを検査 | 欠落・重複・未知版・混在・stale・不正pathで失敗。失敗時に旧成果物を置換しない |
| p400 | 原作のevent/beat/start/end/reveal/preservationを直接投影 | source sceneとruntime sceneの対応、visual notes、完全なsource sceneのauthor入力 |
| p400意味 | 定型blueprint、相反感情、反転、心理、演技・カメラ動作の自動補完を新規v2から除去 | 空の葛藤/turn/追加演出、状態維持、未知の理由がそのまま通る |
| p100/p200 | 既存の共通指示へ成功と代償、誠実な自己説明、既存原作と新作の境界を追記 | 原作の全入力・source refsを維持。新たな心理schemaは追加しない |
| p700 | `intentional_unresolved` と執筆指示を一致。visual notesは読み上げない背景情報へ投影 | 未解決enumが通り、問いの一律回収指示がなくなる。silent/locked/同期の回帰も通る |
| p500 | 固定の「時間制限の光」を素材計画から除去 | 比喩の「壁」がobjectへ増えない。objectのない作品もasset計画へ進む |
| p800 | v2は画像があれば状態維持を許可。画像内容と動作の両方がなければ入力エラー | 無人の岩場に呼吸・重心移動を追加しない。合成unitでもv2を保持 |
| 再開・検証 | 保存済みv2を再読込しhash照合。文字列scene/beat IDを番号へ変えない | p400 rebuildで上流bytes不変。p330/p450のverify-pipelineが通る |

既存v1/markerなしの経路は維持した。新規v2の障害をlegacyへ落として成功扱いにはしない。
既存runの書換え、DB/UI改修、モデル変更、実APIでの画像・動画・音声生成は行っていない。

## 具体的な比較

1. **静かな食事**：変更前は非空のconflict/turnと転換を要求した。変更後は空文字・空mappingと状態維持を受理する。存在しないbeatを参照した転換は引き続き失敗する。
2. **理由が分からない場面**：変更前は固定の圧力や感情推移が入り得た。変更後は観客の「理由は不明」を保持し、mixed affectは未指定ならnone、心理変化は空のままになる。
3. **修理の成功と関係の不確かさ**：「あなたのために直した」という人物の発言と、相手が席を離れる観察事実を異なるsource refsのままscript/manifestへ保持する。実用的成功と関係修復を一つの成長にまとめない。
4. **比喩の壁**：themeだけにある壁はobject bibleへ増えない。実在する道具がない場合も、空のreveal ledgerを架空のartifactで埋めない。
5. **意図的に未解決の結末**：validatorが既に許していた未解決を、promptで一律に回収させる矛盾を取り除いた。
6. **無人の岩場**：v2の動作fallbackに呼吸・重心移動が出ない。何を映すかも動作もない入力はエラーとする。

これらはfixtureの値と出力の比較。任意の原作の忠実さや感動を自動判定したという意味ではない。

## フィールドの扱い

| 種類 | 例 | 新規v2の扱い |
| --- | --- | --- |
| 整合性に必要 | scene/beat/source ID、digest、順序、reveal、handoff、生成前のframe/motion入力 | 必須・参照検証を維持 |
| 作品次第 | 葛藤、dramatic question、心理反転、mixed affect、iconic moment、追加の演出notes | authorが必要な場合に記述。未指定を定型文で埋めない |
| 既存互換 | adaptation_intent、scene_value_amplification、cut expressive_contract | 既存v1で維持、新規v2のplanningとは混在させない |

p400へ別のLLM writerを追加したわけではない。p200の具体的なauthoringをp400で保持し、
p300 notesをauthoring context/script/manifestと下流readsetに渡す。
すべての自由記述notesが最終画像へ意図どおり反映されたという確認はしていない。

## 検証

まず失敗する回帰ケースを追加し、実装後に成功を確認した。
具体例はp300共通author不在、空turnの拒否、固定amplification、未解決promptの矛盾、
無人画像への動作fallback、架空artifactを要求する空reveal、文字列IDの数値検査、
保存済みsourceの変更、動画unitの版情報消失。

主な追加テスト:

- `tests/test_visual_value_source_first.py`
- `tests/test_source_first_scene_projection.py`
- `tests/test_storytelling_semantics.py`

関連する上流・脚本・素材・画像・音声・動画・再開・render・grounding・frontendの29ファイルを実行し、
**445 passed、173 subtests passed**。同時に存在するB-roll変更の回帰テストもこの実行に含めた。
その変更自体は別計画であり、本読書計画の実装としては数えない。
最後の動画unit版検査の修正後は、動画関連とB-rollの4ファイルを再実行し、
**86 passed、117 subtests passed**。

p330/p450停止fixtureでは、テスト内で次の実コマンドも実行して成功を確認した。

```text
python3 scripts/verify-pipeline.py --run-dir <temporary-fixture> --flow immersive --profile fast --stage-target p330
python3 scripts/verify-pipeline.py --run-dir <temporary-fixture> --flow immersive --profile fast --stage-target p450
python3 scripts/validate-slot-contract.py
python3 scripts/validate-pointer-docs.py
```

変更Pythonのcompileallと `git diff --check` も成功。ルートAGENTS/CLAUDEは変更していない。
独立したsubagentレビューは起動せず、差分と入出力経路をローカルで確認した。
新しいauthor入口は既存のread-only runtime、引数配列によるsubprocess、環境変数scrub、
nofollowファイルI/Oとsource digest照合を使用する。source資料内の命令はデータとして扱う。

## 未検証のもの

- 実際のLLMが新promptとnotesに従う精度・速度・コスト。
- 実生成した映像と音声を編集したときの忠実さ、テンポ、余韻、観客への効果。
- 計画の全受入ケースについての作品単位の目視比較。自動回帰の成功で置き換えない。

次の制作時は、この実装で作った新規runを題材にこれらを比較する。常設のcriticや採点gateは追加しない。
