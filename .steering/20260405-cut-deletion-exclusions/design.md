# Design

- manifest/template に `cut_status: active|deleted` と `deletion_reason` を追加する
- parser は deleted cut を通常 node として読み込むが、runtime loop では skip する
- request materialization は deleted cut を本文から除外し、別途 `generation_exclusion_report.md` を出す
- concat list 生成は manifest を YAML として読み、deleted cut の video/audio output を `*_generation_exclusions.md` に送る
- 既存 output path は保持してよい。使う/使わないの判定は status で行う
