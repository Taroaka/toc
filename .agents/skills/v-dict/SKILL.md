---
name: v-dict
description: ユーザーが `/音声辞書`、`音声辞書`、`発音辞書` と言って、漢字・固有名詞・専門語と読みを追加/更新したい時に使う。ToC の ElevenLabs / TTS 読み替え辞書 `config/tts-pronunciation-aliases.tsv` を安全に編集する。
---

# V-Dict

## Overview

ToC の音声生成 API に渡す前の読み替え辞書へ、ユーザー指定の表記と読みを追加または更新する。

このスキルは ElevenLabs API を呼ばない。辞書ファイルだけを更新し、必要に応じて dry-run で TTS payload の読み替えを確認する。

## When to Use

- ユーザーが `/音声辞書 売上 うりあげ` のように依頼したとき
- ユーザーが「発音辞書に追加」「読みを登録」「ElevenLabs の読みを直す」と言ったとき
- TTS 前レビューで誤読しそうな漢字・固有名詞・専門語を見つけ、ユーザーが読みを指定したとき

## Instructions

1. 入力から `surface` と `reading` を抽出する。
   - 例: `/音声辞書 売上 うりあげ` -> `surface=売上`, `reading=うりあげ`
   - 例: `売上=>うりあげ` / `売上=うりあげ` / `売上	うりあげ` も許可する
   - 複数ペアがある場合は全件処理する
2. 読みが曖昧な場合だけ、短く質問する。推測で登録しない。
3. 次のスクリプトを使って辞書へ追加/更新する。

```bash
python .agents/skills/v-dict/scripts/add-entry.py <surface> <reading>
```

4. 通常の保存先は `config/tts-pronunciation-aliases.tsv`。
   - `TOC_TTS_PRONUNCIATION_ALIAS_FILE` が設定されている場合は、そのパスを優先する
   - 明示的に別ファイルへ入れる必要がある場合は `--dict <path>` を使う
5. スクリプト出力の `added` / `updated` / `unchanged` を確認し、ユーザーにどの表記をどう登録したかだけ報告する。
6. 読み替えを確認したい場合は、API を呼ばずに dry-run する。

```bash
python scripts/generate-elevenlabs-tts.py \
  --api-key test_key \
  --text "<確認したい文>" \
  --out /tmp/toc-tts-check.mp3 \
  --dry-run
```

## Examples

Input:

```text
/音声辞書 売上 うりあげ
```

Command:

```bash
python .agents/skills/v-dict/scripts/add-entry.py 売上 うりあげ
```

Result:

```text
config/tts-pronunciation-aliases.tsv に `売上 -> うりあげ` を追加
```

Input:

```text
/音声辞書 竜宮城 りゅうぐうじょう 玉手箱 たまてばこ
```

Command:

```bash
python .agents/skills/v-dict/scripts/add-entry.py 竜宮城 りゅうぐうじょう 玉手箱 たまてばこ
```

## Guidelines

- `surface` は TTS 原稿に出る表記をそのまま入れる。
- `reading` は ElevenLabs に読ませたい文字列を入れる。日本語はひらがな優先。
- 長い表記と短い表記が両方ある場合、長い表記も登録する。
  - 例: `売上` と `売上を取得` では、後者も必要なら別 entry にする
- 読み替えは公開用の `text` ではなく、TTS 直前の `tts_text` に適用される。
- 辞書更新だけでは音声を生成しない。
