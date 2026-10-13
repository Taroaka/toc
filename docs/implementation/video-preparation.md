# 動画生成前の全scene準備

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
python scripts/prepare-scene-video.py --run-id <run_id> --execute \
  --max-images <run-wide-limit> --max-cost-usd <run-wide-budget>
```

`--fixed-image` を繰り返すと、画像修正で変更しないrun相対の `assets/` pathを指定できます。APIでは `scene_ids`、`max_image_generations`、`max_cost_usd`、`fixed_image_paths` が対応します。

## 処理と保持するデータ

準備はsceneのshot設計、参照画像、採用ナレーション、必要な素材bytes、隣接sceneとの関係をsnapshot digestへ結び付けます。採用音声を測り、scene authorが実画像と音声区間を見て、変更不要・視覚設計の変更・追加確認のどれかを返します。音声ファイルや文章を生成・変更する工程ではありません。

初回判断と修正後確認の両方で、authorへ添付する画像はrun内のno-follow読み込み後にsnapshotのhashと照合します。一致した実bytesをprivateな一時directoryへコピーしてから添付するため、変更可能な元pathを直接添付しません。修正後確認では新しい画像に加えて人物・状態などの参照画像も含めます。

設計変更は視覚用の `shot_plan`、投影後のshot/image fieldsに限定します。story、script、source、親cutの意味・音声・尺を変更しないことを検証します。開始stillは既存画像を同じ静的な画像条件で再利用できる場合にreuseします。必要な画像だけ生成し、生成後はscene全体の画像を作者が再確認してからmanifestとrequestを更新します。新しい画像の生成には通常の画像runtimeを使います。

同じsnapshotがready receiptと一致すればそのsceneを再利用し、作者呼び出しや画像修正を繰り返しません。準備中のdraftと送信記録は `logs/video_preparation/` に保存されます。`logs/video_preparation/images/<request-hash>.json` の画像receiptはdraftをまたいでrun内で共有され、同じrequestと参照hashの完了候補についてrun内asset pathとSHA-256を記録します。候補の実bytesが残っていてhashも一致すれば再利用でき、同じ画像を再送しません。画像送信状態が `submitting` のままで結果を確定できないときは `needs_input` に止まり、同じ生成を自動再送しません。出力後に入力snapshotが変わった場合も、そのまま公開せず最新状態での再準備を求めます。

設計や画像に実際の変更がある場合は該当sceneのmanifestを更新し、scene requestを再materializeします。動画prompt materializationはstaleになり、p830はpendingへ戻ります。p840の動画生成はここでは実行しません。変更のないscene/cut、採用音声、既存candidateのbytesは保持されます。

## 画像と費用の範囲

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
