# ナレーション前の画像修正と動画生成前の全scene準備

制作順は `画像生成 → 画像だけで判断できる不一致の確認・修正 → ナレーション/TTS → 実音声との同期確認 → 動画生成` です。人物・衣装・道具・姿勢・接触・位置関係・開始終了画像・隣接場面の継続性は、音声生成を待たずに共通準備サービスの `phase: images` で扱います。音声実尺と発話区間に依存する判断は `phase: video` で行います。

`scene_image_consistency_v1` の完了記録は `logs/image_consistency/` に保存します。現在の視覚設計・原作・参照・実画像のhashに束縛し、ナレーション文・TTS設定・音声bytesだけの変更では無効化しません。画像確認完了を動画準備完了として扱うことはありません。画像生成の送信記録と累積費用は両phaseで `logs/video_preparation/` を共有し、同じロックで並行修正を防ぎます。

新規cinematic run（`video_preparation_policy: scene_video_preparation_v1`）では、自動ナレーション継続、手動のナレーション準備・単体/一括TTS入口が画像確認・修正を先に実行します。未解決なら原稿執筆・TTS送信へ進みません。直接のTTS要求作成にもreadiness検証を置きます。standaloneのasset generatorは画像確認が未完ならTTSの前で停止し、この共通準備CLIの実行を必要とします。markerのない旧runへ遡及適用せず、明示的な `phase: images` 実行で有効化できます。

ユーザー自身による原稿の保存や無音の指定は、画像生成を発生させず引き続き行えます。画像確認を必須とする境界は、自動の原稿作成と実際の音声生成です。

自動の画像phaseは、保存済み累積上限があればそれを保持します。初回は既存の画像対象数（最大500枚）を画像生成回数の上限とし、account認証を必須にする組み込み画像生成の外部API費用を0 USDとして扱います。Codexの利用枠を消費し得ますが、有料APIへの切替やクレジット購入は行いません。明示的な画像単価設定があれば優先し、予算が不足すれば停止します。既存の音声・原稿・親cut尺は画像修正で変更しません。

`scene_video_preparation_v1` は、動画を送信する前にscene全体のshot設計と画像を採用音声・実画像に合わせる共通経路です。演出担当が対象sceneを確認し、必要な場合だけ視覚設計を修正し、必要な修正画像を準備してからsceneをreadyにします。動画providerへの送信やp840完了記録は行いません。

## 入口と実行範囲

フロントは既存の `CutDirectionPanel` に含まれる `VideoPreparationPanel` を使います。APIは `server/video_preparation_api.py` が登録する次のrouteです。

| 操作 | 経路 | 効果 |
| --- | --- | --- |
| 状態確認 | `GET /api/image-gen/video-preparation?run_id=<run_id>` | 無課金で状態を読みます。provider生成や書き込みはしません。 |
| 準備開始 | `POST /api/image-gen/video-preparation` | 非同期で共通準備を開始します。作者の判断と、必要な範囲内の画像生成があり得ます。 |
| 実行中の取消 | `POST /api/image-gen/video-preparation/cancel` | 実行中の準備taskを中断します。送信結果が不明な生成を再送する操作ではありません。 |

同じサービスをCLIからも使います。`--execute` がない場合は無課金の状態確認だけです。APIのPOSTまたはCLIの `--execute` を明示すると、未readyのsceneにはscene authorによる判断を行い、許可された上限内で必要な画像修正を生成する場合があります。同じsnapshotがreadyなら既存結果を再利用します。`--scene-id` は複数回指定でき、省略時はrun内の全sceneが対象です。

```bash
python scripts/prepare-scene-video.py --run-id <run_id>
python scripts/prepare-scene-video.py --run-id <run_id> --phase images --execute \
  --max-images <run-wide-limit> --max-cost-usd <run-wide-budget>
python scripts/prepare-scene-video.py --run-id <run_id> --execute \
  --max-images <run-wide-limit> --max-cost-usd <run-wide-budget>
```

`--fixed-image` を繰り返すと、画像修正で変更しないrun相対の `assets/` pathを指定できます。APIでは `scene_ids`、`max_image_generations`、`max_cost_usd`、`fixed_image_paths` が対応します。

APIの開始body、状態GETのquery、取消bodyは `phase: images|video` を受け付けます。省略時は従来の `video` です。CLIは `--phase images|video` が対応します。以下の音声・動画費用を含む説明はvideo phaseの契約です。

## 処理と保持するデータ

準備はsceneのshot設計、参照画像、採用ナレーション、必要な素材bytes、隣接sceneとの関係をsnapshot digestへ結び付けます。採用音声を測り、scene authorが実画像と音声区間を見て、変更不要・視覚設計の変更・追加確認のどれかを返します。音声ファイルや文章を生成・変更する工程ではありません。

初回判断と修正後確認の両方で、authorへ添付する画像はrun内のno-follow読み込み後にsnapshotのhashと照合します。一致した実bytesをprivateな一時directoryへコピーしてから添付するため、変更可能な元pathを直接添付しません。修正後確認では新しい画像に加えて人物・状態などの参照画像も含めます。

作者入力は `toc/video_preparation_context.py` の読み取り専用投影を使います。物語全文、対象sceneのscript、全編の語りとユーザー修正、演出意図、親cutの契約・尺・音声、shot plan、画像参照と隣接境界を保持し、実行用payload・trace・派生したchild契約・過去の音声候補を重複して送りません。snapshotとcanonical artifactは省略せず元のbytesへ束縛します。投影後も入力上限を超える場合は送信前に止め、原文の切り捨てで通しません。

設計変更は視覚用の `shot_plan`、投影後のshot/image fieldsに限定します。story、script、source、親cutの意味・音声・尺を変更しないことを検証します。開始stillは既存画像を同じ静的な画像条件で再利用できる場合にreuseします。必要な画像だけ生成し、生成後はscene全体の画像を作者が再確認してからmanifestとrequestを更新します。新しい画像の生成には通常の画像runtimeを使います。

同じsnapshotがready receiptと一致すればそのsceneを再利用し、作者呼び出しや画像修正を繰り返しません。準備中のdraftと送信記録は `logs/video_preparation/` に保存されます。`logs/video_preparation/images/<request-hash>.json` の画像receiptはdraftをまたいでrun内で共有され、同じrequestと参照hashの完了候補についてrun内asset pathとSHA-256を記録します。候補の実bytesが残っていてhashも一致すれば再利用でき、同じ画像を再送しません。画像送信状態が `submitting` のままで結果を確定できないときは `needs_input` に止まり、同じ生成を自動再送しません。出力後に入力snapshotが変わった場合も、そのまま公開せず最新状態での再準備を求めます。

設計や画像に実際の変更がある場合は該当sceneのmanifestを更新し、scene requestを再materializeします。動画prompt materializationはstaleになり、p830はpendingへ戻ります。p840の動画生成はここでは実行しません。変更のないscene/cut、採用音声、既存candidateのbytesは保持されます。

## 画像と費用の範囲

再修正前の差分判定は、保存先や実行用メタデータを除いた静的な画像条件を比較します。新しい開始画像を参照する終了画像は、開始画像が生成された後、送信直前に参照bytesをhashへ束縛します。未生成の参照を先読みしたり、保存先の変更だけを不一致の解消と見なしたりしません。

修正画像の確認が `needs_input` になった場合、同じコマンドの再実行はその記録を保持して停止します。指摘を反映した再修正は `review_revision: 1`（CLI: `--review-revision 1`）を明示します。最大3回で、各回は同じsnapshot・固定画像・選択モデルに対応する直前の不一致記録を必要とします。過去draftを消さず別checkpointに保存し、完成候補の実bytesをrequest/hashに照合して作者へ渡します。変更cutだけを前回案へ統合し、同じ画像条件を再採点して通すことはしません。未変更の画像候補と累積費用予約を再利用し、追加画像は従来の上限内だけで生成します。上限を増やす前に、保存された新しい案と実request差分から必要枚数を確認します。

追加画像はprovider送信前にrun累積の `CostLedger` へ予約します。既存画像や同一requestの完了候補を再利用する場合は、新たな画像送信と画像費用予約を行いません。画像候補を見積なしで再利用できるとは限らず、修正対象がある実行では画像上限見積と予算入力が必要です。CLI/APIの `max_images` / `max_image_generations` と `max_cost_usd` は、1回の呼び出し分ではなく `logs/video_preparation/costs.json` に残るrun累積値の上限です。

server環境変数で、各画像の上限見積 `TOC_PREPARATION_IMAGE_COST_UPPER_USD` とvideo生成秒あたりの上限見積 `TOC_PREPARATION_VIDEO_SECOND_COST_UPPER_USD` を設定できます。準備時には変更されたvideo requestごとにprovider生成尺×既定3候補で概算します。同じ生成尺のままprompt等が変わったrequestも、新しい生成が必要なものとして見積に含めます。この段階の動画費用は事前見積で、CostLedgerへの動画費用予約ではありません。必要な見積設定または実行時の累積予算上限がない場合、あるいは見積が上限を超える場合は `needs_input` になります。

p840の送信直前には、実際のcandidate数、request、durable media operation IDを束縛して動画費用を `CostLedger` へ予約します。予約額は実際に送るcandidate数×各requestのprovider生成尺に基づきます。上限見積が未設定、または累積予算上限を超える場合は送信前に止まります。

このledgerは、設定した上限見積に基づくrun内の予算管理です。providerの実請求額を保証したり、provider側の課金を直接制限したりはしません。実請求は見積と異なる可能性があります。

画像修正用のshot projectionはHiggsfield Kling 3.0 Standard用です。既に各対象cut/shotで `tool: higgsfield` と `model: kling-video/v3.0/std/image-to-video` が設定されている場合、または準備前のモデル選択でStandardを明示した場合に使えます。Kling Omniや別provider/modelからKling 3.0 Standardへ黙って切り替えません。合わない場合は `needs_input` で止まります。

## p830/p840のreadiness

新しいcinematic runのうち `cinematic_direction` から作られたrunには、`video_preparation_policy: scene_video_preparation_v1` が設定されます。準備実行時はsceneを指定しない限りrun内の全sceneが対象です。p830のrequest作成とp840の動画生成にあるreadiness guardは、今回の対象itemが属するsceneだけを検証します。そのsceneのready receiptが現在のsnapshot digestと一致することを確認し、別sceneが未準備でも、準備済みsceneのitemは進められます。manifestや参照bytesが変われば、そのsceneのreceiptは再利用されません。

既存runにはmarkerを遡及して追加しません。既存runで準備APIのPOSTを明示的に実行するとrunのpreparation状態が有効になります（CLIの `--execute` も同じserviceを使います）。以後のp830/p840 guardは毎回、対象itemが属するsceneのreadyだけを確認します。`scene_ids` を絞った準備と部分的な動画生成も可能です。

## 動画provider送信journal

動画生成時の送信保護はこの準備処理とは別に、既存のmedia generation経路で行います。KlingとSeedanceは、providerへのPOST前にrequest hash付きintentを保存し、受理後にoperation/task IDを直ちにrun内journalへ永続化します。送信結果不明のintentは自動再送しません。Higgsfieldは従来のadapter journalを継続して使います。

この説明は実装上の契約を記録したものです。paid video providerへのend-to-end API生成確認は未実施です。

## 実装の入口

- 共通サービス: `toc/scene_direction_service.py`
- API、Kling向け投影、manifest/request publication: `server/video_preparation_api.py`
- APIを使うCLI: `scripts/prepare-scene-video.py`
- provider submit journal: `toc/provider_submission_journal.py`
- フロントの入口: `server/web/src/CutDirectionPanel.tsx` 内の `VideoPreparationPanel`

## 準備前のモデル選択

準備APIの `target_video_model` は未指定/nullなら現在の設定を保持し、`higgsfield_kling_standard` は全対象sceneをHiggsfield Kling 3.0 Standard用のshot設計へ移す明示指示です。既存のOmni設定を無通知で変更しません。フロントの準備パネルで選べ、CLIでは `--target-video-model higgsfield_kling_standard` を使います。旧親cutの音声・原作契約・元の設定は保持し、実行する子shotに選択を投影します。
