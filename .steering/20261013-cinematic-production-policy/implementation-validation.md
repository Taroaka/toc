# 実装・検証記録 — 2026-10-13

## 実装した内容

- 共通scene準備: `toc/scene_direction_service.py`。全sceneが既定対象。実画像・採用音声bytes・時間区間・原作・隣接境界を束縛し、変更不要／視覚設計修正／要確認を保存する。
- 視覚投影共有: `toc/visual_cut_projection.py`。既存cut editorと新sceneサービスが同じ純粋な投影処理を使い、親音声・原作契約・確定尺を保持する。
- 実画像author入力: 構造化runtimeにlocal_imagesを追加。新サービスはno-follow読込・hash一致を確認したbytesをprivateな一時コピーにし、そのコピーを添付する。
- 画像修正: 必要画像だけを既存生成APIへ渡す。旧素材は保持。生成requestと参照bytesが同じ完了候補はrun内receiptから再利用する。不明な送信は自動再送しない。修正後も人物/状態参照を添付して同じ担当が確認する。
- 予算: 画像は送信前に回数/上限見積額を永続予約。動画は変更request全体と既定3候補を準備時に見積もり、p840では実候補数とoperation IDを使って送信直前に予約する。実請求額の保証ではない。
- 公開・再開: 対象sceneの依存値をcommit直前に再照合し、manifest/request/state/indexをtransactionで公開する。旧MediaJournalのrun全体hashチェックは緩めない。
- provider journal: Kling/SeedanceはPOST前intent、受理IDのpoll前永続化、IDがある場合のpoll再開を追加。Higgsfieldの既存journalは維持。
- 入口: API、`scripts/prepare-scene-video.py`、会話用の画像/動画スキルを接続。フロントに状態・画像回数・費用枠・固定画像・中断・明示モデル選択を追加。
- 新規cinematic runに準備policy markerを付ける。旧runは閲覧だけでは変更しない。p830/p840は生成対象sceneの現在の準備結果を確認する。
- 準備前の明示モデル選択: `target_video_model=higgsfield_kling_standard` でStandardを選べる。nullは設定保持。Omniから黙って切り替えない。

## 検証結果

| 確認 | 結果 |
|---|---|
| 共通準備/API/既存cut editor/author runtime/provider journal/shot/p400/materialization/音声尺/画像snapshotのバックエンド回帰 | 221 passed、4 subtests passed |
| 最終の準備状態表示・中断表示の小修正 | 該当core/API 33 passed（中断・表示の確認、必要画像修正が実行されないままreadyにならない確認を含む） |
| フロント単体テスト | 60 passed |
| TypeScript + Vite build | 成功 |
| 実request materializerとの接続 | 一時fixtureで実スクリプトを呼び、新scene commit後のshot snapshot作成に成功 |
| 通常p830の設定保存 | aspect ratio等の既定値が補われても準備結果は有効。音声・実参照・mode等の実値変更は無効になる |
| 実ブラウザ | Chromeで開始→poll→完了・親refreshと中断を確認。650pxパネル、390px画面で横overflowなし。APIはmock、実API通信/POSTは0件。previewにログ・画像を保存 |
| pointer docs | `Pointer docs valid.` |
| 導入済み会話スキル | 画像/動画のSKILL.mdを個人用ディレクトリへ同期しbytes一致。変更前のバックアップを同steering配下に保存 |

各テスト実行は重複するため、件数を合算して総数とはしない。FastAPIの既存on_event非推奨警告と、Viteの既存chunk-size警告が残る。

## レビューで解消した点

- 準備済みsceneが別sceneの未準備で止まらないよう、p830/p840の対象scopeを限定。
- 同じ尺の撮り直しと複数候補の費用を計上。予算不足をHTTP409で返す。
- 実素材のすり替えを避けるため、authorへの添付をprivate snapshotへ変更。
- 次sceneの入口・前sceneの出口だけを入力とsnapshotに含める。
- assets bible形式の参照、動画first/last/references、input_modeをsnapshotへ束縛。
- 修正画像確認にもidentity/state参照を添付。
- モデルの無通知切替を禁止し、準備前の明示選択を追加。
- request作成時に欠けていたprovider capabilityのinput_modeを渡す修正を追加。
- indexをtransactionへ含め、state更新後に再構築。

独立のコードレビューとセキュリティレビューで、対象指摘の修正後に重大な残りがないことを確認した。これは実モデルが望む演技を一発で生成する保証ではない。

## 今回実施していないこと

- 本番run/既存シンデレラ素材の変更、再生成。
- 実際の有料author、画像、音声、動画APIへの生成要求。
- 別の物語1本の実生成・全編視聴。有料実行前に作品・原資料・モデル・費用上限・出力仕様・音響範囲を決める。
- 新規providerやnative multishotへの対応。画像修正を伴う現行shot投影はHiggsfield Kling 3.0 Standard。

金額上限見積の環境設定がない場合、必要な生成はneeds_inputで止める。未設定の料金を推定で補わない。準備のauthor利用自体は既存のCodex利用枠を使い、provider向けUSD予算とは別。

## 適用上の補足

- 演出authorが画像の不備を見つけた場合は、対象画像を明示し、開始/終了画の不足条件を具体化した設計差分を出す。差分がなく必要画像が修正されない提案をreadyにしない。
- 準備状態は採用素材と別のoperation記録へ保存し、変更不要のsceneでも完了状態をappend-only stateとindexへ反映する。
- 最終buildはアプリ同梱の対応Node.jsで実行し成功。

## ローカル環境への反映

新APIが稼働中のbackendへ未読込だったため、既存ToC listenerと生成leaseが開かれていないことを確認して公式restart helperを実行した。helperはlistener停止後、Docker APIへ接続できずDB起動で停止した。Docker UI確認もタイムアウトしたため、それ以上のUI操作は行っていない。

DBの設定・volume・role・データは変更せず、既存runtimeとloopbackポートでbackend/frontendを復旧した。HTTP応答とOpenAPI上の新準備routeを確認。Docker側APIの不調と、別に稼働しているnative PostgresにはToC用roleがない問題は未解消。DB依存機能を含む本番全編制作の確認は行っていない。

- Frontend: http://127.0.0.1:5173/image_gen/
- Backend: http://127.0.0.1:8000/image_gen
- 起動ログ: `.codex/run/toc-server/backend.log` / `frontend.log`
- 本番生成は開始していない。
