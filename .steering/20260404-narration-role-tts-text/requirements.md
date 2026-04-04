# Requirements

## Context

現在の narration evaluator は「映像だけでは分かりにくい情報を最低1つ追加する」を強く要求しており、物語序盤でも因果語や抽象語を無理に差し込んだ不自然な文を通しやすい。また ElevenLabs 向けの読み上げでは漢字の読み崩れがあり、表示用本文と TTS 入力を分ける必要がある。

## Goals

1. narration evaluator を scene/cut の物語上の役割に合わせて評価する
2. 序盤では「その物語の導入として安定しているか」を重視し、非視覚情報の追加を必須にしない
3. ElevenLabs 向けに `audio.narration.tts_text` を持てるようにし、生成時はそちらを優先する
4. docs / templates / multiagent scratch を新運用に合わせる

## Non-Goals

1. 既存 run の音声を自動再生成すること
2. 漢字からひらがなへの自動変換器を新規依存付きで導入すること

## Functional Requirements

1. `scripts/review-narration-text-quality.py` は sibling `script.md` を読める場合、scene phase や scene/cut narration を参照して role-aware に評価する
2. role-aware rubric は少なくとも `opening / middle / ending` を区別できる
3. opening では「見たまま説明」だけを一律 fail にせず、script に沿った導入文を許容する
4. middle / ending では従来どおり補完・意味付け・余韻を評価できる
5. `audio.narration.tts_text` がある場合、`generate-assets-from-manifest.py` はそれを ElevenLabs / macOS say に送る
6. `audio.narration.tts_text` が無い場合は既存どおり `audio.narration.text` を使う
7. manifest parser / multiagent merge は `tts_text` を保持できる

## Verification

1. narration review tests が opening 許容 / role mismatch / contract 互換を確認する
2. manifest parsing / multiagent merge tests が `tts_text` を保持する
3. 既存 verify 系テストが壊れない
