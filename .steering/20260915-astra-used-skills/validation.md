# 判断例の確認

改訂文面と現行実装を照合した手動確認。別モデルの実行結果や実サービスのテスト結果ではない。

| 依頼例 | 改訂後の判断 | 確認 |
| --- | --- | --- |
| Reactの文字を1か所直す | 汎用の設計例全読込・coverage/E2E一式を要求しない | 発動条件とtdd/verificationの低影響変更の扱い |
| タブ切替が遅いので原因を調べる | frontendの必要な参照だけを読み、対象操作を計測 | 状態・性能の資料分離、既存ライブラリの尊重 |
| 回帰バグを直す | 意図した失敗を表すテスト、実装修正、影響する検証まで進む | TDDの本旨・既存coverage規則を保持 |
| 別ユーザーのファイルが取得できるかレビュー | 入力から認可・保存先まで追跡し、証拠付きで報告 | security-reviewの境界別確認 |
| `/review` だけ | 未コミットの対象差分をレビューし、指摘を返す | SKILLとUI default_promptの両方で修正依頼を区別 |
| Astraでレビュー、委任許可なし | ローカルで確認し、独立レビューとは主張しない | 現行エージェント方針を優先 |
| SPECは確定済み、GOAL.mdを作って | 既決基準を再承認させず作成。goalの開始は別 | 未決の製品判断だけ質問し、budgetを発明しない |
| workspace-write環境でgoalを準備 | 許可された作業を進め、必要な権限は該当操作で扱う | 旧model/context/full-accessを要件にしない |
| serverの状態だけ確認 | health check、再起動helperは実行しない | check/restartを分離 |
| 既存runの画像タイムアウトを再試行 | APIがlease内でp650/p500を選び1ジョブを開始 | `ResumeRunRequest`と`api_resume_run`を照合。POSTは実行で、CLI追加起動を禁止 |
| p650は不正、assetがstale | fresh p400が有効ならp500のplan/apply | checkpoint ID/token・上流hash・quarantine・append-only stateを保持 |
| 新規runをp680まで | 正式runnerで生成とoutput検証まで完遂 | p650早期停止・materialize-onlyをp680成功としない |
| 重要アイテムを設計して | canonical asset bibleを作り参照整合を確認 | 設計依頼だけで画像生成へ進まない |
| LPの価格を直す | marketingの価格正本を読む | routerに価格を複製せず既存の価格/人数/比較条件を維持 |

## 構造検証

- 14種類のfrontmatter検証、相対リンクの実在、既存metadataの保持: 成功。
- フロント/バックエンドの移動した例: 元セクションと一致。
- 変更はMarkdownおよびreviewスキルのUI YAMLだけ。既存のシェル/Pythonスクリプトは変更しない。
- `goal-forge` の旧config inspectorは互換用の既存ファイルとして保持するが、現行readinessには使わない旨を入口・参照・READMEに明記。
- 既存shared skill testの1件の失敗は対象外スキルの固定文言によるもの。対象のみの形式検証と配布一致検証を別途実施する。

適用後: 33配布ディレクトリの形式検証成功、74更新文書のhash一致、それ以外の既存ファイルのhash不変、対象差分の `git diff --check` 成功。shared skill testは変更前と同じ1件だけが失敗。
