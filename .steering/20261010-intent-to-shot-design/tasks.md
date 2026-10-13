# 実装予定と確認項目

状態: 2026-10-13 実装・検証完了。確定事項はdecision.md、検証結果はimplementation-validation.md。native multishotと有料生成による画質確認は今回の範囲外。

## 今回

- [x] 既存projection、camera/performance、nullable、provider境界を調査
- [x] 一次資料と未確認事項を記録
- [x] 意図・演技・可視範囲・撮影・参照・実送信の設計を作成
- [x] 赤ペンシートを作成・表示検証し、Codexの表示要求を送信（queued）
- [x] ユーザーの赤ペン回答を受け取る

## 回答後の順序

- [x] Q1〜Q3を反映し、version付き契約と互換読込のfixtureを先に定義する。
- [x] p400の作者入力/出力と`cinematic_language`を拡張。音声採用済みのvisual-only更新、member別performance、world/viewの分離を実装。
- [x] p400 projectionとimage compilerで、開始画の参照・被写体・部分描写を分離。result frame/state variantsの既存機構へ接続。
- [x] video compilerで、動作/カメラ/reveal/状態継続を独立投影。無言の切捨てと役割由来の人物禁止を新versionで解消。
- [x] Higgsfield Kling Standardをprovider/model/modeの検証済み範囲で共通経路へ追加。未確認elements等は未対応のまま保持。
- [x] frontend、CLI、conversation skillが同じrequest snapshotを読むよう接続。Q2の一覧UIと訂正の反映、Q3の選択cut更新を実装。
- [x] stage docs/templates/会話用image・video skillsを同期。code reviewと関連テストを実施。

## 動作を守るテストケース

| 入力 | 守る期待 |
|---|---|
| 途中から人物が映る | 初期画像のpositive subject/refsに混入しない。後半のidentity/state参照は消えない |
| 最初から全員が見える | 不要な入場eventを作らない |
| 足元、手元、背中 | 正しい人物・衣装参照を使い、顔や全身を要求しない。subの人物禁止で落とさない |
| 人物なしの画 | 空subject/performanceを許し、必要な場所・構図は残す |
| カメラだけで人物が見える | 世界の所在/状態を変えない。物理的入場と区別する |
| 動作の物理的前提が画面外 | 手・道具・相手の存在条件を保持しつつ、開始画へ全て描かせない |
| 受け渡しと相手の反応 | actor/target、契機、順序を保持。全員同時の表情へ潰さない |
| 人物が動き、衣装は維持 | 衣装継続を人物静止に変換しない |
| 変身と後続cut | state variant/result frame/採用衣装を正しく引き継ぐ |
| null / [] / 欠落 / 未解決 | 項目別の意味と継承解除を守り、未解決の必須参照は送信しない |
| cameraの複数操作 | 異なる意図を無言で切り詰めず、適切な分割/解決を要求する |
| 採用音声を保ったvisual-only更新 | 音声bytes/hash、原稿、区間・scene全体尺が不変 |
| 1音声区間→複数shot（Q1採用時） | shot割当てに意図しないgap/重複がなく、clip余剰は明示trim |
| 古いmanifest / 新規manifest | 旧意味を保持し、新版のみ新投影を使う |
| 画像/衣装/原稿の更新 | 影響するrequestだけstale。採用mediaは自動破棄しない |
| frontend/CLI/会話の同じ入力 | 同一prompt、参照hash、モデル、尺のsnapshotになる |
| 未対応の参照方式 | 素材を黙って捨てず、shot単位で具体的な不足を表示 |

実画像の自然さ、演技の成功、後半登場の遵守は上記構造テストと別。承認済みの範囲で少数の生成結果を確認して限界を記録する。
