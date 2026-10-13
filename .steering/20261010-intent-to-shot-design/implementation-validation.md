# 実装・検証記録 — 2026-10-13

## 実装した経路

- `toc/shot_direction.py`: 意図、人物の目的・感情・演技、最初に見える対象と部位、撮影、登場/退出、任意の終了画を持つversion付きJSON。不要な演出指定はnull/空配列を許可。
- `toc/shot_projection.py`: 開始画の被写体/参照とcut全体の参加者を分離し、child shotの画像/動画へ投影。後半の参照を黙って捨てず、参照できない配置は生成前に返す。
- `toc/shot_timeline.py`: 親の採用済み音声・合成区間と、個別APIの生成尺を分ける共有検証。
- `server/cut_direction_api.py` / `scripts/edit-cut-direction.py`: 同じ処理による一覧取得と選択cutの自然文/JSON編集。revision・source・request snapshotを照合して保存。
- `CutDirectionPanel.tsx`: 前後cutとshotの一覧、意図・画角・動き・部位・参照・音声尺の確認。既存の画像ギャラリーとchild IDで選択を同期。
- Higgsfield Kling 3.0 Standard: provider/model/input modeを束縛。開始/終了画像、モデル既定画質、3–15秒の整数尺、音声offを共通adapterへ送る。CLIも同じadapterを使う。
- 合成: childごとに既存の承認・入力hashを確認し、余剰尺をtrimして親cutの区間へ配置。ナレーションは親cutに一度だけ残す。
- 新規/選択cutのみ新版を適用。編集時はplan hashを出力名に入れ、既存の採用メディアを上書きしない。

## 検証

| 確認 | 結果 |
|---|---|
| 関連バックエンド広域回帰（shot/editor/provider/server/p400/素材状態/画像snapshot/動画prompt/合成/音mix） | 642 passed、219 subtests passed |
| 最終のshot/editor/runtime重点回帰 | 53 passed |
| CLI/provider/動画materialization・projection回帰 | 61 passed、60 subtests passed |
| CLIレビュー修正後のrequest-preview回帰 | 70 passed、42 subtests passed |
| CLIレビュー修正後のprovider/server/CLI回帰 | 47 passed、13 subtests passed |
| フロントの最終単体テスト | 55 passed |
| TypeScript + Vite production build | 成功 |
| 実コンポーネントのブラウザ操作 | mock APIを使った隔離ブラウザで、JSON保存・自然文保存・再表示・エラー表示・再読込を確認 |
| 実materializerとの接続 | 一時runで実際のgenerate-assetsスクリプトを実行し、構造検証とsnapshotの一致を確認 |
| 採用音声の尺 | 元の予定4秒・採用後8秒で、親の音声・元の予定値を変更せずshot合計8秒となることを確認 |
| ffmpeg | childの承認不足を拒否し、小数秒のtrimと結合を検証。音声set/timeline hashは不変 |
| セキュリティレビュー | timeout/cancel時の子プロセス停止・回収を修正し、rollback後に書込みが続かない回帰2件に合格 |
| pointer docs / skills / whitespace | 成功。画像・動画・シーン設計の3スキルを登録済み個人スキルへ同期し、bytes一致を確認 |

件数はそれぞれのコマンド実行結果であり、重複するテストを合算していない。既存のFastAPI on_event非推奨警告とVite chunk-size警告は残る。

## レビューで修正した事項

- `その後`等で演技の後半を切る処理、カメラ指示の機械的な切捨てを新版shotでは使わない。
- 未来の出来事の説明文を、shotのprovider向け禁止文へ流さない。
- 変身済みの人物/物だけ状態variantを継承する。まだ起きていない結果状態を開始画へ流さない。
- 変身対象とresult referenceの人物ID・variant・source beat・実pathを一致させる。別人の結果参照で代用しない。
- 直前shotの終了画を次の開始画の参照にできる。画角変更は別に指定する。
- 巨大整数、case-insensitiveなID/出力衝突、不正な区間、未解決の参照を生成前に拒否する。
- runtime数値scene IDと原作のsemantic scene IDを区別し、自然文編集へ正しい原作・前後の撮影を渡す。
- CLIのrequest journalをrequest hashごとに分離し、以前の不明な送信状態を消さない。Klingの明示的な解像度指定は捨てずに拒否する。

コードレビューとセキュリティレビューの指摘は修正し、最終確認でblockerなし。UIのSHA-256 revision型とchild/parent選択の接続も最終テストへ反映済み。

## 今回行っていないこと

- ユーザーの作品・原稿・採用音声・画像・動画の変更や再生成。
- 有料生成APIによる映像品質の確認。
- provider native multishot。複数shotはそれぞれ別requestとして生成する。
- 未確認のHiggsfield elements参照機能。対応しない参照を黙って省略するfallbackは設けない。

JSONと参照・送信・尺の結合は検証済みだが、生成モデルが演技や構図をどこまで再現するかは、実際の作品で別途確認する範囲。
