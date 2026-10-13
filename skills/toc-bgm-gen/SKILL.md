---
name: toc-bgm-gen
description: >
  スレッドからToC作品のBGMを音楽生成APIで作成・再生成するよう依頼されたときに使う。「BGMも生成して」「ElevenLabsで劇伴を作って」など、実際の音楽音源を求める依頼が対象。最新の物語進行、映像・語り、採用曲、cue配置、無音楽区間と実送信設定を確認し、必要な設計をして生成する。音楽案・prompt作成だけ、仕様・料金の質問、音量調整や既存曲の配置だけ、TTS・SE生成では起動しない。
---

# ToC BGM生成

ToCルートを特定し、`docs/implementation/conversation-media-generation.md` を読む。
音響の正本は `docs/implementation/sound-design.md`。
`docs/research/film-sound-emotion.md`、`workflow/playbooks/sound-design/affect-and-spotting.md`、
`workflow/sound-spotting-template.md` を読み、既存のp860設計を使う。

## 物語と音楽を照合する

- scene/全編の流れと、その時点の開示内容、採用映像の実尺・順序、ナレーションと台詞、
  native audio、既存 `sound_design.json` のcue/候補/mixを確認する。
- 鳴らす目的、聴点、始める/変える/止める理由を設計する。cutごとに定型BGMを付けない。
  音楽なし・環境音のみ・全無音を区別し、結末や未来の出来事を音楽で先取りしない。
- 既存主題を継承する場合は採用音源とその箇所を特定する。
  独立した音楽生成でも同じ旋律が再現される、または参照音源が送られたとは推測しない。
- cueのprompt、生成尺、タイムライン上の開始/配置尺、loop、fade、個別gain、BGM系統gainを区別する。
  感情を固定の楽器や一律の低音量に機械変換しない。

## 実行と引き渡し

`server/sound_design_api.py` の共通設計/候補生成経路と、
`toc.sound_design.provider_request` の実payloadを確認して使う。
ElevenLabsなら音楽operationであることを確認し、TTSへ音楽の指示文を送らない。
実model、長さの単位、instrumental/vocal指定、出力formatを照合する。
許可していない歌声・語り・台詞を加えない。利用adapterの対応外の指定は黙って落とさない。

p860の通常の動画承認・revision/video hash条件を守る。ユーザーが未確定映像での試作を
明示した場合は、scopeと仮タイムラインを記録した別preview候補にし、canonicalな動画承認や
p860完了を偽装しない。後で映像が変われば配置を見直す。

生成前に実requestを保存し、共通手順に従って結果不明の二重送信を避ける。
音源のdecode/尺/hashを確認し、歌声や余韻等を実際に確認した範囲を伝える。
元音源とmix設定を保持して採用候補として保存する。再mixだけなら再生成しない。
結合を依頼されたら、確定したcue配置と3系統mixerを使い、正式出力と試聴版を区別する。
