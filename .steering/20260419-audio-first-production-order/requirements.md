# Audio-First Production Order Requirements

## Goal

- 固定 `p-slot` workflow を production order に合わせて再編する。
- 後半順序は `narration/audio -> asset -> scene implementation -> video -> render` を正本にする。
- `video_manifest.md` は narration 用 skeleton と scene/video 実装用 production の二段階 lifecycle を持つ。
- 変更理由を各正本 doc に残し、同じ議論の再発を減らす。

## Requirements

- `p500` は narration/audio runtime を表す固定帯に変更する。
- `p600` は asset stage、`p700` は scene implementation、`p800` は video stage に変更する。
- `p400` には skeleton manifest materialization slot を追加する。
- stage grounding の canonical stage を `narration`, `asset`, `scene_implementation`, `video_generation` に揃える。
- 既存 run は one-shot migration で新 contract に移行する。
- image/video generation は `manifest_phase=production` でなければ開始しない。

## Non-Goals

- `script.md` や `video_manifest.md` の filename rename。
- provider 実装の全面刷新。
- 旧 slot 番号の runtime 互換 reader 維持。
