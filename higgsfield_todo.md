# Higgsfield TODO — ToC / Cloud Codex handoff

更新日: 2026-10-07（Asia/Tokyo）

## 目的と決定済み事項

ToCの動画生成にHiggsfield公開APIを接続する。Codexプラグイン経由ではなく、公開API専用のドル残高を使う。既存のKling/Seedance連携と承認済み素材を維持し、cut単位で生成・保存・再実行できるようにする。

ユーザーの必須条件:
- 人物・衣装・背景など、複数の参照画像を渡せる。
- 開始画像と終了画像を指定できる。
- 秒数を指定できる。
- 特に「追加参照画像＋開始画像＋終了画像」を同時に使えるか確認する。個別の入力欄があるだけで同時対応と判定しない。

2026-10-07追記: ローカルToCへの動画連携実装、自動テスト、サーバー反映まで完了。
Higgsfield公開APIでの有料生成は、ユーザーの明示指定により実行しない。実アカウントのモデル利用可否と生成結果は未検証。

## ローカルで実装済みの範囲

- 動画画面でHiggsfield / Seedance 2.5を選択できる。
- image-to-video: 開始画像＋任意の終了画像。reference-to-video: 順序付き複数参照画像。
- 両モードの同時併用は拒否。4〜30秒、480p/720p/1080p、生成音声OFF/自然音/原作台詞と音に対応。
- 参照数32はToCの入力上限であり、Higgsfieldが32枚を受理するという保証ではない。
- requestの確定、素材upload、submit、ID保存、poll、保存済みIDからのresume、出力検証・候補保存まで実装。
- 受付不明時の自動再送を防ぎ、認証値はserverだけで扱う。生成動画の音はp860で採用・消音・音量調整できる。
- API呼出しをmockにした結合テストで候補保存と再開を確認。実動画/音声の検証・mixはローカルffmpegで確認。
- 新規モデル全体の自動取込やHiggsfield経由のKling接続は含まない。既存Kling接続は維持する。

実装・検証記録: `.steering/20261007-cinematic-language-and-sync-audio/validation.md`。
下記のクラウド準備・実生成・作品固有の制作TODOは別途残る。

## ローカル反映後の確認（2026-10-07）

コードと`docs/vendor/higgsfield.md`、既存validationを照合し、次の専用テストを再実行した。

- Python: `tests/test_higgsfield_provider.py tests/test_higgsfield_integration.py` — **18 passed**。外部APIはmock。ローカルffmpegで動画検証も実行。
- フロント: `src/HiggsfieldSettings.test.ts` — **6 passed**。
- この確認では生成API・素材upload・有料生成を実行していない。既存validationに記載の広域テスト/build/サーバー反映は今回再実行していない。
- 下記のチェック済み項目は実装とローカルテストの完了であり、実アカウント上の生成成功を意味しない。

優先して残る項目:
- [ ] 開始/終了＋複数参照の同時利用要件を解決する。**現実装は明示拒否**。選択式でよいか、同時対応の公式操作・モデルが必要かを決める。
- [ ] 参照画像の実provider上限を確認する（ToC入力上限32と区別）。
- [ ] 費用見積り・画面表示を接続する。現在のadapterと画面では実装を確認できないため、下記フロント接続の複合項目は未完のままにする。
- [ ] provider側キャンセルの実装範囲を決める。現在のHiggsfield adapterはsubmit/statusが中心でcancel操作はない。poll停止を課金処理の取消しと表示しない。
- [ ] 実アカウント認証/モデル利用可否を確認後、ユーザーが実生成の再開を指示した段階で1cutを試す。
- [ ] シーン9の夜版へのデータ/画像/原稿変更を行う（下記制作TODO）。

## P0: クラウド作業の準備

- [ ] このファイルと必要な実装差分をクラウドのcheckoutへ同期する。
  - Git remote: `https://github.com/Taroaka/toc.git`。確認時のローカルbranchは`main`。
  - ローカルには多数の未コミット変更がある。クラウドcheckoutに同じ変更があると仮定しない。全変更をまとめてcommit/pushしたり、resetしたりしない。
  - ローカルrepo: `/Users/kantaro/Downloads/toc`。ChatGPTプロジェクトの`sources/`は読み取り専用の参照であり、実repoと混同しない。
- [ ] クラウド環境のsecretに`HF_API_KEY`を設定し、実行時に利用できることを確認する。
  - ローカルの`.env`に保存済み。Git管理外、権限0600、`toc.env.load_env_files`で読み込み確認済み。
  - 値はこの文書に含めない。ローカルの`.env`はクラウドへ自動転送されない。他サービスの認証情報を含む`.env`全体を送らない。
  - ユーザーは有効期間を30日に設定した。2026-10-07に受領。正確な失効時刻は未確認。
  - RESTの認証は`Authorization: Key <HF_API_KEYの完全な値>`。SDKを使うなら、そのSDKが要求する環境変数へサーバー内で明示的に渡す。
- [ ] クラウドのネットワーク許可、必要ライブラリ、ffmpegを確認する。既存の環境設定を優先する。
- [ ] 実生成時に必要なrunデータ・素材を明示的に同期する。
  - 対象run: `output/シンデレラ_20260926_1554`。`output/`はGit管理対象外。
  - `research.md`, `story.md`, `visual_value.md`, `cinematic_direction.json`, `script.md`, `video_manifest.md`, `ending_extension.json`、依存する参照台帳、画像・音声、承認記録が必要。
  - 最初の接続実装とモックテストは、素材同期が未完でも進められる。ローカル絶対パスをクラウドで使わない。

## P1: APIの能力と入力の組合せを確定

- [ ] API公式モデルカタログから候補と操作別スキーマを読む。プラグインのモデルIDをAPIのパスとして使わない。
- [ ] 下記をモデル・入力モードごとの対応表にする。
  - 複数参照の最大枚数、順番、人物/衣装/背景の役割指定。
  - 開始・終了フレームと追加参照の同時指定可否。非対応の入力を黙って捨てない。
  - 最小/最大秒数、秒数の刻み、解像度、16:9、音声OFF。
  - カメラ指示、単一連続shot、禁止事項の指定方法。専用フィールドとpromptによる指示を区別する。
  - 費用見積り、アップロード、状態取得、結果取得、キャンセル、出力URLの保持期間。
- [ ] 課金しない認証確認と利用可能モデル/残高の確認を、公式にある操作で行う。残高確認URLを推測しない。
- [ ] 不明な入力組合せは未検証と記録し、小さな実生成で確認できる条件を用意する。

確認済みの参考情報（2026-10-07、契約/稼働保証ではない）:
- プラグインのKling 3.0は開始/終了、3〜15秒、音声OFFを公開。追加参照入力はモデル詳細にない。
- プラグインのSeedance 2.5は参照画像/動画/音声と開始/終了のroleを列挙し、4〜30秒を公開。同時利用の制約・枚数は未確定。
- 公開APIのSeedance 2.5 `reference-to-video`は`image_urls`配列を持つ。`image-to-video`とは別操作。同じリクエストで開始/終了を併用できるとはまだ確認していない。
- 公開APIのKling 3.0 Pro I2Vは`image_url`, `last_image_url`, `elements`, `cfg_scale`, `multi_shots`, `multi_prompt`を公開。`elements`を任意画像配列と解釈しない。

## P2: ToCへ公開APIを接続

- [x] 変更前に`.steering/`へ要件・設計・taskを記録し、既存provider契約と整合させる。
- [x] 汎用Higgsfield provider adapterを追加する。作品固有の人物・cut・固定promptを実装に埋め込まない。
- [x] `HF_API_KEY`をバックエンドだけで読む。`.env.example`には空欄のみ追加。キー・Authorization・署名付きURLをログ/画面に出さない。
- [x] 公式アップロード手順で参照素材を送る。PUT成功後にだけpublic URLを採用。ストレージへのPUTにAPI認証ヘッダーを流用しない。
- [x] submit → request ID保存 → status/result → ローカル保存を実装する。
  - 通信タイムアウトで受付成否が不明なPOSTを自動再送しない。
  - 再開時は保存済みrequest IDを追跡し、二重課金を避ける。
  - 失敗したcutだけを再実行でき、既存の合格候補を上書きしない。
- [x] モデル能力に合わせて、manifest → compiled payload → immutable request snapshotを作る。
  - prompt、画像順序/role/hash、秒数、画質、音声設定、provider/model、request IDと出力を紐付ける。
  - 合わない設定はエラーとして返す。画像を減らす・秒数を変える・別モデルにする等を無断で行わない。
- [ ] ToCのフロントにprovider/model、参照role、開始/終了画像、秒数、費用・状態・候補動画を接続する。
- [x] 出力のdecode、実測尺、解像度、ストリーム、hashを確認して既存renderへ渡す。
- [x] 既存のKling/Seedance経路を維持し、未検証を理由に既存選択肢を消さない。

関連実装/正本:
- `toc/env.py`
- `toc/providers/kling.py`, `toc/providers/seedance.py`
- `server/image_gen_app.py`, `server/image_gen.py`
- `server/web/src/main.tsx`
- `docs/video-generation.md`
- `docs/implementation/video-prompting.md`, `docs/implementation/video-integration.md`
- `workflow/playbooks/video-generation/kling.md`

注意: 現行ToCのKling adapterも追加参照画像を送れず、明示エラーにしている。Kling本体の全能力がToCで使える状態ではない。

## P3: 検証と最初の実生成

- [x] ハーネス/全pipelineを回さず、対象のテストコードで確認する（ユーザー指定）。
- [x] 単体テスト: 入力roleの保持、非対応組合せの拒否、音声OFF、秒数境界、認証値非露出、受付不明時の重複防止、途中からの再開、ファイル保存とprovenance。
- [ ] 既存動画provider・ナレーションの必要な回帰テストと、変更した場合のみフロントbuildを行う。
- [ ] 最初は1cutだけ、モデル/入力組合せ/尺/費用を具体化して試す。全61cutを一括生成しない。
- [ ] 映像を見て、人物の顔・服装、手、表情、開始/終了状態、カメラ移動、勝手なshot切替がないか確認する。
- [ ] 生成した映像を既存音声と合わせ、先頭0.5秒と終わりの余韻を確認する。

## 制作側の未完了: シーン9を夜の終幕に変更

ここはAPI接続作業と分けて進める。夜版の変更・画像/音声/動画生成はまだ実行していない。

現在の保存済み状態:
- 9 scenes / 61 cuts（既存58cut＋scene90の3cut）。
- scene90は昼の城内で手を取る/微笑む/寄り添う構成。開始画像3枚とJunの旧原稿候補音声あり。
- 約21秒の旧確認動画は静止画を並べた絵コンテであり、AI生成の動く動画ではない。
- 旧語り: 「シンデレラの隣には、喜びを分かち合う人がいました。」

ユーザーが採用した新しい終幕:
- テーマ: 大切にされなかったシンデレラが、大切な人と安心できる居場所を得る。
- cut1: 夜の城の窓辺。二人が手を重ね、目を合わせて微笑む。表情を十分に見せる。
- cut2: シンデレラが王子の肩に寄り添い、カメラが窓の外へゆっくり離れる。暖かい窓明かりの中に二人を残す。
- cut3: 城の外から星空へ引く。編集で「シンデレラ」を静かに表示し、余韻を置いて暗転する。
- 新しい語り: 「その夜、シンデレラは、大切な人の隣で、安心して笑っていました。」
- 声はJun、ですます調、落ち着いた語り。`[Warm, calm narration, slow measured delivery]`をTTSに入れ、公開原稿と分ける。
- 最後のタイトル・フェードは編集工程。動画モデルに文字を描かせない。BGMは音声と映像の尺が固まった後。

- [ ] 新しい夜の終幕をstory/visual/cinematic_direction/script/manifestと創作出典記録へ整合させる。
- [ ] 夜版の人物参照と開始/終了画像を用意し、旧画像を履歴に残す。
- [ ] 新しい語りだけを生成する。既存シーンの音声を再生成しない。
- [ ] 窓から外へ抜けるcutを最初の映像試験にする。難しければcut境界を設計し直し、勝手に場面を飛ばさない。

維持すべき音声条件:
- ユーザー発言「シーン8までの音声cutは合格です」を記録済み。
- 既存58cutの音声情報とTTS文脈は前回追加時に維持確認済み。
- Jun voice ID: `JOcmGzB8OFjY8MhjHHEf`、実行実績モデル`eleven_v4`。
- 継母→新しい母、義姉→義理の姉（TTS: 義理のあね）、シンデレラ本人を指す娘→シンデレラ、真夜中のTTS→マヨナカ。
- 有声cutの動画尺は少なくとも`ceil(実測音声秒数 + 0.5)`。無音cutと余韻の尺も保持する。
- scene1は現行原稿revisionに一致する音声候補がない点が残る。古い音声に新revisionを偽装して紐付けない。`narration_approval_through_scene80.json`を参照し、再生成を勝手に行わない。

## 完了条件

- 必須入力の同時利用可否を、公式スキーマと実際のリクエストで説明できる。
- ToCからHiggsfield公開APIへ1cutを生成・追跡・保存・表示し、既存音声と合成できる。
- 原稿/画像/設定と生成物の対応が追跡でき、再開時に二重生成せず、既存合格素材が変わらない。
- クラウド/ローカル双方の設定方法、未検証事項、実生成費用を記録する。

## 公式参照

- https://open.higgsfield.ai/quick-start
- https://docs.higgsfield.ai/docs/llms.txt
- https://open.higgsfield.ai/explore
- https://higgsfield.ai/creator-hub/help-center/integrations/what-is-the-higgsfield-api
- https://open.higgsfield.ai/models/bytedance/seedance-2.5/reference-to-video/api-reference
- https://open.higgsfield.ai/models/kling-video/v3.0/pro/image-to-video/api-reference

## クラウドCodexへの開始文

`higgsfield_todo.md`を読んで、ToCへのHiggsfield公開API連携を進めてください。まずP0のcheckout/secretの有無とP1のモデル能力を確認し、足りない素材に依存しない実装・モックテストを進めてください。プラグインのクレジットは使わず、既存の合格済み音声と素材を保持してください。全pipeline/harnessの実行ではなく、対象テストで検証してください。APIキーをログに出さないでください。夜の終幕は設計合意済みですが、まだ保存済みの昼版から変更されていません。
