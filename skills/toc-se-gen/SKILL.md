---
name: toc-se-gen
description: >
  スレッドからToC作品の効果音・環境音をSE生成APIで作成・再生成するよう依頼されたときに使う。「SEも作って」「ElevenLabsで足音を生成して」など、実際の効果音源を求める依頼が対象。最新映像の動作・材質・距離・発生時刻、採用音源と実送信設定を確認する。既存SEの音量相談・試聴も生成設定とmixを切り分けて扱い、音量変更だけでは再生成しない。効果音案だけ、API仕様の質問、BGM・ナレーション生成では起動しない。
---

# ToC SE生成

ToCルートを特定し、`docs/implementation/conversation-media-generation.md` を読む。
`docs/implementation/sound-design.md`、`docs/research/film-sound-emotion.md`、
`workflow/playbooks/sound-design/affect-and-spotting.md` と既存p860のcue設計を読む。

## 音の根拠と同期を確認する

- 最新映像の動作、接触、材質、距離、空間、出来事の順序と実発生位置を確認する。
  prompt内で予定した時刻を、生成映像上の実際の発生時刻とみなさない。
- 当該cutの前後、ナレーション/台詞、環境音、動画由来音声、BGMとの役割・重複を確認する。
  画面外の音は設計上の根拠と聴点を持たせ、未設定の出来事を音だけで追加しない。
- cueの目的、生成する音の具体的な要素、生成尺と配置尺、開始時刻、loop/fade、
  個別gain・SE系統gainを決める。全cut冒頭への一律配置はしない。
- 映像変更で作業・足音・変身等が消えた場合は旧cueを残さず、必要な配置変更を設計する。
  削除/不採用と生成を分け、旧候補ファイルは保持する。

## 実際の生成指示を確認する

`server/sound_design_api.py` の共通候補生成経路と
`toc.sound_design.provider_request` が返すendpoint/payloadを照合する。
ElevenLabsではsound-generation operationを使い、TTSへSE指示文を送らない。
発話を意図しない効果音は非発話として指定する。笑い声などを意図する場合は、
誰のどんな非言語音かを音響設計で区別する。制作指示を読ませない。

実model、duration、loop、prompt influence、format等の対応値を確認する。
`prompt_influence` やvoice設定を音量調整値として扱わない。
「小さい/控えめ」の生成指示、生成音源自体の音量、mixのgain、ナレーションの正規化を分ける。
音量の相談では実設定と必要な音量測定を確認して原因を説明し、
調整だけで足りる場合は音源を再生成しない。

## 結果を扱う

p860の通常の承認・revision/video hash条件を守り、明示された未確定映像向け試作は
別previewとして扱う。仮の同期位置を最終確定と記録しない。
共通のjournal・再開・decode/尺/hash確認を行い、実映像に合わせて配置する。
指示文や不要な発話の混入は、試聴等で実際に確認した場合だけ「確認済み」と報告する。
採用音源と音量設定を保存し、結合依頼があれば共通mixerで視聴できる形にする。
