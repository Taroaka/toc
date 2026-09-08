# /toc-scene-series

ToC を topic/source から複数 scene の Q&A 縦動画へ変換する command。

## 使い方

```text
/toc-scene-series "桃太郎" --min-seconds 30 --max-seconds 60
/toc-scene-series "桃太郎" --scene-ids 2,4 --min-seconds 30 --max-seconds 60
/toc-scene-series "桃太郎" --dry-run
```

## Output

```text
output/<topic>_<timestamp>/
  state.txt
  research.md
  story.md
  series_plan.md
  scenes/sceneXX/
    evidence.md
    script.md
    video_manifest.md
    assets/
    video.mp4
  logs/grounding/
  logs/orchestration/
  logs/validation/
```

本文（question、narration、prompt）は日本語で記録する。scene script は evidence の source IDs
と question/answer を保持し、30–60 秒の target duration と provider capability を使う。

## Flow

```text
source context → research → story → series_plan
  → scene evidence → scene script
  → scene/cut manifest → image/audio/video generation
  → scene render and ordinary output checks
```

scene ごとに prepare-stage-context.py を使い、required docs/templates/inputs を読み、
schema/type/ID/reference/request/file/decode/duration/provenance を確認する。shared
research.md と series plan は single writer、scene directory は scene owner が更新する。

## Scene authoring

- question は concrete な viewer question にする。
- answer/evidence は evidence.md の source refs に結び付ける。
- cut は one intent、image first-frame、motion boundary、narration role、downstream handoff を持つ。
- --dry-run は provider call をせず、構造化 artifact と request payload を作る。
- candidate selection/listening/editing は任意の user action として保存できる。
- contradictory source の hybridization と publication は明示した user action として扱う。

## References

- docs/how-to-run.md
- docs/data-contracts.md
- docs/implementation/scene-loop.md

