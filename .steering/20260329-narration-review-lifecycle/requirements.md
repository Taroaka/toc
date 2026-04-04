# Requirements

## Goal

ナレーション原稿（`audio.narration.text`）にも、画像 prompt review と同型の「subagent 評価 -> 修正 -> 再 review -> human override」ループを導入し、TTS に不向きな原稿を音声生成前に止められるようにする。

## Requirements

- 対象は repo-wide の narration review lifecycle とする
- 対象 field は `video_manifest.md` の各 renderable node にある `audio.narration.text` とする
- review 結果は source manifest 自体に書き戻す
- review field は image prompt review と同じ意味体系で扱う
- `agent_review_ok: false` の場合は reason key を 1 つ以上残す
- false reason は、TTS 向け修正対象が分かる短い key で扱う
- narration review は ElevenLabs `eleven_multilingual_v2` を標準モデルとする現在運用に合わせ、v3 向け audio tag など v2 に不向きな入力を false にできる
- narration review は、数字 / URL / 英字略語 / 記号などの未正規化、句読点不足、長文、TODO/メタ混入、映像指示語漏れを機械的に検出できる
- 修正は source manifest に反映してから再 review する運用を正本化する
- 人間 override は subagent finding を消さず、例外許容を記録する契約にする
- 画像 prompt review と同様に、assets 生成フローへ pre-audio gate として組み込む
