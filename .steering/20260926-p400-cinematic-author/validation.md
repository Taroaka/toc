# p400 Cinematic Author — 実装・検証

2026-09-26。ユーザーが承認した「LLMが映画として設計し、コードが検証・実行形式へ変換する」方針を実装した。

## 新規制作の処理

1. p300成功後、p400契約markerをstateへ記録する。
2. 実際の制作profileから人物・物・場所と衣装のregistryを作り、共通read-only authorを起動する。
3. sceneごとにresearch/story/visual全文、全編の流れ、直前sceneの完成したcut列を読み、演出とcut列を執筆する。
4. source参照・beat順序・開示許可・状態の接続・使用素材・尺を検証。不備は該当sceneのauthorへ返して最大2回修正する。
5. 全sceneが成功したらsource hash付き `cinematic_direction.json` を保存する。
6. 既存scene-set preflightを維持し、専用projectionでscript/manifestへ変換する。旧cut planner・均等尺配分・定型語りを通さない。
7. 正本公開前とstage検証でcanonical projectionを再生成し、意味に関わる契約のずれを検出する。

## LLMが決め、保持されるもの

- scene全体の演出、p300の意図の具体化、前後sceneとの接続。
- cut数、複数beatの長回しへの統合、一beatの分割。
- primary subject、構図・画角・焦点・光、カメラの動き。
- 開始画、動作、終了状態、動作のどの時点を映すか。
- 語りの役割と本文、理由付き沈黙、音の意図、切る理由。
- cutごとの不均等な秒数。現行共通provider能力表の範囲で検証する。

世界の状態と画面に見せる範囲を分離した。continuous接続は状態IDとfactsを引き継ぐが、
次cutで同じ絵を要求しない。例えば机上の箱の状態を保ったまま、人物の顔だけのclose-upを選べる。
省略はellipsisと専用理由を記録する。場面の開始/終了状態IDはsourceの状態IDへ束縛する。

## 失敗・再開

- author失敗、source変更、未知版、source/asset不整合は失敗する。旧機械処理で代替しない。
- 全scene完了前の失敗では既存directionを置換しない。通常のnofollow/atomic書込を使う。
- 新契約開始後にdirectionが失われても、state markerによりlegacyへのdowngradeを拒否する。
- 保存済みdirectionは再投影に使う。既存の未移行runの従来経路は保持する。
- p400 rebuildの新契約candidateにはdirectionも含め、script/manifestとsource hash・projectionを検証する。
- p700が更新する語り本文・実測尺は、p400の計画尺と意味境界から区別する。

## 回帰ケース

`tests/test_p400_cinematic_author.py` で次を確認した。

- 全文と前sceneの完成出力がauthor promptに残る。
- 不均等な尺、沈黙、カメラ判断、前後cut参照が保存される。
- 旧cut plannerと均等配分関数を例外に置き換えても、新しいbuilderが成功する。
- 未知asset、別sceneの人物、欠落beat、不正尺、不正連続性、不正開示を拒否する。
- 先行cutが後続beatのreveal許可を前借りできない。
- continuous接続で閉じた物を開いた状態へ書き換えると、状態factsの照合が失敗する。
- 状態を保持したまま画角を変え、画面外の物を描かない設計が通る。
- 原作の保持条件、未来の禁止出来事、既存の衣装が実行用画像promptまで残る。
- 動作前/結果/余韻などの時間位置と、suspended momentを保持する。
- 修正ループの成功と上限、source変更、symlink拒否、旧成果物の保持。
- 設計ファイル不変でも、投影先のsource facts・asset IDs・前cut状態・時間位置を変えると失敗する。
- ellipsisの理由とmodeを下流契約へ保持する。
- p450の実verify-pipelineと、providerを呼ばないrequest-file materializationが成功する。

## レビュー

独立したcode-reviewerで確認し、reveal許可の広すぎる範囲、時間位置の固定値、
可読な未来境界・原作保持条件・衣装bindingの欠落、projection照合不足、ellipsis理由の欠落を修正した。
固定のfirst-frame文面を要求すると構図変更を妨げるため、状態factsとvisible stateの分離へ改めた。
コードの正しさと、実際の映画の意味・演出の良さは別に評価する。

## 実行した検証

最終の関連26テストファイル: **422 passed、190 subtests passed**（70.06秒）。
追加したp400専用テストは27件。独立レビューの最終確認でも27件が成功し、確認範囲の追加must-fixなし。
`validate-slot-contract.py`、`validate-pointer-docs.py`、変更Pythonのcompileall、`git diff --check` は成功。
生成サービスへのリクエストファイルは一時fixtureで作成し、画像・音声・動画のAPIは呼んでいない。

## 未検証

実モデルによる演出執筆の品質・所要時間・コスト、実生成した映像/音声、編集後の映画としての完成度は未検証。
状態factsやsource IDの構造一致は、自然言語の意味や生成された画面の物理的な正しさを一般に保証しない。
音の意図は下流へ渡すが、未対応のJ/Lカットや自動音響編集を実装済みとはしない。
