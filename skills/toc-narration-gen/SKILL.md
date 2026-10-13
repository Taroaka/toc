---
name: toc-narration-gen
description: >
  スレッドからToC作品のナレーションをTTS・音声生成APIで音源化・再生成・再開するよう依頼されたときに使う。「ElevenLabsで読んで」「指定の声でナレーションを作って」などの音声生成が対象。原稿・読み方・voice ID・採用音声・尺を照合する。「この既存音声を採用して」も取り込みとして扱い、再生成しない。原稿執筆だけ、API仕様の質問、BGM・SE生成では起動しない。
---

# ToC ナレーション音源生成

ToCルートを特定し、`docs/implementation/conversation-media-generation.md` を読む。
`python scripts/prepare-stage-context.py --stage narration --run-dir <run_dir> --flow <flow>`
でreadsetを解決する。`docs/implementation/narration-prompting.md`、
`docs/implementation/video-integration.md` と採用・candidateの契約を読む。

## 音声を作る前に

- `script.md` の表示原稿、同期されたmanifestの `audio.narration`、`tts_text`、
  `narration_style.json`、読み替え辞書、声の指定、原稿/音声revisionを照合する。
  原稿変更が必要なら `toc-narration` の執筆経路で直してからTTS用へ同期する。
- 直前・直後の語り、spanの分割、人物の呼び方、開示の順序と意味を確認する。
  無音cutやB-rollへ音声を自動で埋めない。
- 採用音声の実体と、tmp・previewに置かれた候補を区別する。
  「この音声を使う」は対応する原稿/voice/hashを確認して取り込み、TTSで作り直さない。
  その音声の原稿revisionが現行と異なる場合も、明示された採用を取り消さず、
  元のrevision・原稿・voice・hash付きの承認済み外部素材としてrun内へ保存する。
  現行revisionから生成した候補であると偽装せず、現行cutとの紐付け/整合確認は未完と記録する。
  原稿も音声に合わせるか等、未解決の選択だけを確認し、原稿を黙って巻き戻さない。
- 声の表示名だけでなく実 `voice_id` を解決し、model、言語、voice settings、
  output format、読み指定・タグ・前後文脈を実送信値で確認する。
  別の人物/性別/voiceへ黙って代替しない。声が未指定ならrunの採用設定を確認する。
- 話す本文と制作指示を分ける。SE/BGMの指示、カメラ・演技の説明、パス等を読ませない。
  音声タグは選択modelで対応するものだけ使い、実 `tts_text` への反映を確認する。

## 生成・実測・採用

フロントと同じp730 candidate経路を使う。
実装の入口は `server/image_gen_app.py` の `narration-items`、
`narration-generate` / `narration-generate-bulk`、音声採用処理。
リクエストschemaは現在の実装から確認し、revisionの競合検出を省かない。
未採用candidateを作っただけで、採用音声や確定尺を上書きしない。

生成後はdecode、実測秒数、無音/欠落、hashを確認する。読み方・指示文混入を
試聴等で確認していない場合は、確認済みと報告しない。
採用された音声に対してoffsetとspan配置を含む尺を反映し、影響する動画だけを示す。
既存映像へ収まらない場合はその差を伝え、語りの速度変更・原稿短縮・動画再生成を
無断で行わない。声だけ直す依頼で無関係な画像/BGM/SEを生成しない。

原音は保持し、音量の正規化は `toc/narration_audio.py` の共通方針に従う。
声の生成設定と、最終mixでのナレーション音量を別々に記録する。
