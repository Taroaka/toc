---
name: toc-video-gen
description: >
  スレッドからToC作品のcut・sceneを動画生成APIで生成・再生成・再開するよう依頼されたときに使う。「動画を作って」「全cutを生成して」「Higgsfield/Klingで作り直して」など、APIやスキル名が省略された実生成の依頼も対象。物語の進捗、採用画像・終了画像、ナレーション実測尺、修正指示と実送信設定を照合して実行する。仕様・料金の質問、モデル比較、prompt作成だけでは起動しない。
---

# ToC 動画生成

ToCプロジェクトのルートを特定し、以下のパスはそこを基準に読む。
最初に `docs/implementation/conversation-media-generation.md` の共通確認を行う。
スキルを適用しただけで生成権限が追加されるわけではない。

## 設計と尺を復元する

- `python scripts/resolve-stage-grounding.py --stage video_generation --run-dir <run_dir> --flow <flow>`
  で対象flowのreadsetを解決し、該当資料を読む。
- `docs/video-generation.md`、`docs/implementation/video-prompting.md`、
  `docs/implementation/video-integration.md`、使用providerのplaybookを確認する。
- 対象ごとに、直前の状態→開始状態→主動作→終了状態→次cutとの接続を説明できるようにする。
  人物の登場経路、人数、道具の受け渡し、衣装、視線、移動を終える/続ける条件を設計と照合する。
  全キャストの `cast_design` があれば、登場人物の役割・区別点・所作の基調も読む。
  見た目が似て別の人物に見える、役割が入れ替わる等の問題は参照画像の段階で特定する。
  性格の基調で各場面のsourceにある行為や反応を上書きしない。
  魔法の煙、固定カメラ、お辞儀などを全作品共通の演出にはしない。
- `shot_plan` があるcutはリポジトリの `docs/implementation/shot-direction.md`を読み、各child shotを個別のvideo requestとして扱う。親cutの音声とtimelineは維持し、provider native multishotへまとめない。現在のprojectionではKlingへ整数の3〜15秒を要求するため、fractional timeline尺と生成尺を分け、親cutへ組み立てる際に生成clipの余分な尺をtrimする。
- 衣装も後続場面へ引き継ぐ状態として、主人公以外を含む全人物を確認する。
  共通手順の「衣装は人物ごとに引き継ぐ状態」に従い、直前の採用映像、当該cutの開始画像、
  中間/終了画像と実payloadで、人物ごとの色・形・袖・靴の対応を照合する。
  集合名の一人分の素材を全員に複製せず、古い人物素材の衣装へ戻さない。
  衣装や人物との対応が食い違う画像は、修正してから動画生成へ渡す。
- 採用音源の実パス/候補/hashを特定してffprobeで測る。最新の生成物が採用版とは限らない。
  offset、間、複数cutをまたぐspan、無音cutの予定尺を含め、現在の音声配置から必要尺を決める。
  単一cutの音声は少なくとも実測秒数＋offsetを収める。整数秒指定なら現行方針のceilで切り上げ、
  既存requestの短い秒数をそのまま再利用しない。spanは全体の配置を保って照合する。
  固定済み音声を、対応秒数へ収めるために無断で高速化・低速化・省略しない。

## 実際の参照と設定を照合する

- `video_manifest.md` と現在の `video_generation_requests.md` の対象・prompt・設定を照合する。
  上流の修正はcanonicalな設計へ反映し、既存compiler/materializerでrequestを作り直す。
- 変化がある場合は前後の状態素材を確認する。終了画像は毎回追加せず、設計で必要な場合に
  同じ構図のscene-specific画像を用意する。開始画像を終了画像へ自動で兼用しない。
  required `result_state_reference` に対応するp500のvariantとp600の `result_frame` が必要。
  素材シートや次cutの画像を、場面・登場物を確認せず終了画像に代用しない。
- 共通手順の「開始画像と終了画像の差を実画像で照合する」に従い、実送信する組を
  並べて確認する。姿勢・表情等の意図した差と、衣装の細部・付着位置・人物・道具の
  意図しない差を分け、連続動作で到達できない差は画像/設計から直す。
  「服装を維持」とpromptへ書くだけで、矛盾する画像を送らない。途中の生成結果も確認する。
- 人物のやり取りは「行為のあとに何が起きるかを設計する」も確認し、物を動かすだけで
  終わらず、目的に合う表情・視線・応答が読める時間を現在の尺に配分する。
  終了画像を使う場合はその反応に合わせ、喜びや認知をsourceに反して一律に追加しない。
- フレーム式なら実payloadのfirst/last欄、参照式なら実配列と順序・役割を確認する。
  ファイルの存在、画像内容、hash、upload先との対応を追い、promptへの名前記載だけで済ませない。
- provider/model/operation、対応mode・尺・比率/解像度、native audioの実設定を確認する。
  別ナレーションを使う場合も、native soundを勝手にon/offにせず採用した音響方針に合わせる。
- providerの上限を超えるcutは、許可された分割/延長方式で配置を設計する。
  連続shotの後半は実際の前半末尾を参照し、前半の動作や変身を繰り返さない。
  指定尺と生成尺・trim位置を分けて記録する。モデルや速度を黙って変えない。

## 実行と出力

共通手順のsnapshot・送信journal・再開・revision照合を使う。
Higgsfieldを使うときは `docs/vendor/higgsfield.md` と現在のadapter対応を読み、
Higgsfield経由の別modelを同じadapterで扱えると推測しない。
未対応の明示指定APIでは公式schemaと実送信欄を確認して同等の記録を残す。

生成結果はdecode、尺、比率、必要なaudio streamとhashを確認する。
動作・参照の見た目を確認した範囲と、未確認部分を区別して伝える。
依頼に結合が含まれる場合は、採用ナレーション/BGM/SEと既存render経路でプレビューを作る。
動画の再生成だけなら、無関係な音源を再生成しない。

全sceneの撮影準備が必要なrunでは、生成前に [`docs/implementation/video-preparation.md`](../../docs/implementation/video-preparation.md) のreadinessとsnapshotを確認し、未readyなら共通準備経路を実行してからp830/p840へ進む。
