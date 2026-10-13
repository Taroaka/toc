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
  魔法の煙、固定カメラ、お辞儀などを全作品共通の演出にはしない。
- 採用音源の実パス/候補/hashを特定してffprobeで測る。最新の生成物が採用版とは限らない。
  offset、間、複数cutをまたぐspan、無音cutの予定尺を含め、現在の音声配置から必要尺を決める。
  単一cutの音声は少なくとも実測秒数＋offsetを収める。整数秒指定なら現行方針のceilで切り上げ、
  既存requestの短い秒数をそのまま再利用しない。spanは全体の配置を保って照合する。
  固定済み音声を、対応秒数へ収めるために無断で高速化・低速化・省略しない。

## 実際の参照と設定を照合する

- `video_manifest.md` と現在の `video_generation_requests.md` の対象・prompt・設定を照合する。
  上流の修正はcanonicalな設計へ反映し、既存compiler/materializerでrequestを作り直す。
- 変化がある場合は、前後の状態素材と、同じ構図のscene-specific終了画像を確認する。
  required `result_state_reference` に対応するp500のvariantとp600の `result_frame` が必要。
  素材シートや次cutの画像を、場面・登場物を確認せず終了画像に代用しない。
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
