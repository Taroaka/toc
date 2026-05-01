# Requirements

## Context

現在の `script.md` は ElevenLabs 向けの `tts_text` を「v2向けひらがな spoken form」として扱っている。  
この前提だと、v3 の audio tag / 文脈付きテキスト設計を `script.md` に表現しづらい。

今回の変更対象は **`script.md` の ElevenLabs 関連部分のみ** とし、  
ナレーションの情緒価値や runtime 側の v3 消費ロジックは後続 slice で扱う。

## Goals

1. `script.md` で ElevenLabs v3 向けの構造化 prompt を cut 単位で持てる
2. `tts_text` を「ElevenLabs v3 に送る最終文字列」として再定義する
3. 既存の `tts_text` only script は後方互換で読める
4. script authoring 用の template / docs / agent prompt を新 contract に揃える

## Non-Goals

1. `video_manifest.md` / runtime review / TTS 実行コードの v3 本対応
2. ナレーションの内容設計、story role rubric、anti-redundancy 方針の変更
3. voice_id / voice selection 戦略の変更

## Functional Requirements

1. `script_metadata.elevenlabs` に v3 用 default 設定を持てる
2. `scenes[].cuts[].elevenlabs_prompt` は少なくとも `spoken_context` / `voice_tags` / `spoken_body` / `stability_profile` を持てる
3. `voice_tags` は bracket なしの生タグを順序付き配列で保持する
4. `tts_text` は `spoken_context + [tag][tag] + spoken_body` の materialized text として扱う
5. `human_review.approved_tts_text` は既存どおり最優先 override として扱う
6. `elevenlabs_prompt` が無い既存 cut は `spoken_context=""`, `voice_tags=[]`, `spoken_body=<tts_text>` とみなせる
7. 新規 template / generator / authoring prompt は `elevenlabs_prompt` と `tts_text` を両方出す
8. voice tag の default 運用は物語位置で分ける。導入/通常 narration は `gentle` を軸にし、締め/教訓 narration は `low + measured` を軸にする
9. `stability_profile` は voice tag と別軸で保持し、`gentle` 系 tag 運用を置き換えない
10. ElevenLabs v3 の `spoken_body` / `tts_text` は、必要に応じて漢字かな交じりの自然な日本語を許可する。音声品質を優先する cut では、ひらがな正規化より自然表記を優先できる
11. `spoken_context` は常用しない。音声品質や尺を優先する場合は空にし、必要な演技は `voice_tags` へ集約する

## Verification

1. materialization helper の unit test が通る
2. `sync-narration-from-script.py` が `elevenlabs_prompt` fallback を読める
3. template / prompt fixture が新 field を含む
