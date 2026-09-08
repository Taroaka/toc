# /toc-run

ToC を topic/source から実行する command。production は source context → authoring →
ordinary structural validation → generation の順で進む。

## 使い方

```text
/toc-run "桃太郎" --dry-run
```

## 出力

```text
output/<topic>_<timestamp>/
  state.txt
  p000_index.md
  research.md
  story.md
  visual_value.md
  script.md
  video_manifest.md
  assets/
  audio/
  video.mp4
  logs/grounding/
  logs/orchestration/
  logs/validation/
```

本文は日本語で記録する。cut は編集単位、narration span は文章/演技単位として分ける。
音声を明示的に省略したい場合だけ `--skip-audio` を使う。

## Production order

```text
research → story → visual_value → script
  → asset → scene_implementation/image
  → narration/TTS → video → render → qa
```

p400 は scene/cut authoring と skeleton manifest materialization を行う。p500 以降で request
payload を materializeし、画像/音声/動画を生成する。

## Source context and checks

stage ごとに `prepare-stage-context.py` を使い、返された readset を
`global_docs → stage_docs → templates → inputs` の順で読む。各 author は schema、type、unique
ID、source/reference/selector、request hash、file/decode、duration、provenance を確認する。
不足入力や failed check は該当 artifact を修正して再実行する。

## Human choices

Research は候補を複数作ってもよい。候補選択、candidate listening、画像/音声編集、change request
は任意の user action として保存する。矛盾 source の hybridization と publication は、それぞれ
明示された user action として扱う。

## References

- docs/how-to-run.md
- docs/data-contracts.md
- docs/orchestration-and-ops.md

