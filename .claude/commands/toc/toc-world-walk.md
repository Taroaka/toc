# /toc-world-walk

既存 ToC run の story.md と assets/ を参照し、観察者 POV の world-walk video を作る command。

## 使い方

```text
/toc-world-walk --source-run output/桃太郎_<timestamp>
/toc-world-walk --source-run output/桃太郎_<timestamp> --topic "桃太郎の世界観を散歩してみた"
/toc-world-walk --source-run output/桃太郎_<timestamp> --stage script
```

## Concept

- 観察者 POV、少し遠目の中景〜遠景で source world を歩く。
- 主人公本人の主観視点に置き換えない。
- 派手な介入、急接近、劇的な戦闘強調を避ける。
- 序盤は asset/world continuity を見せ、中盤以降に source character が遠景へ現れる。
- source run path、asset IDs、reference bytes を manifest に記録する。

## Arguments

```text
--source-run output/<topic>_<timestamp>     required
--topic <topic>                             optional
--stage research|story|visual_value|script|asset|scene_implementation|narration|video_generation|render
--video-tool kling|kling-omni|seedance|veo   optional
```

stage execution uses source context → authoring → ordinary structural validation → generation.
`script.md` and `video_manifest.md` remain canonical; the source run is read-only.

## Helpers

```bash
python scripts/toc-world-walk.py --source-run output/桃太郎_<timestamp>
```

The helper may use `scripts/toc-immersive-ride.py --experience world_walk --source-run ...`.
When stage is omitted, stop after script/skeleton manifest authoring. Frontend create uses the same
backend production path and request/provenance checks.

## Prompt requirements

Include observer POV, stable horizon/camera height, natural walking speed, visible path/leading line,
source asset continuity, and no on-screen text. Exclude selfie, shoulder-close view, abrupt zoom,
intervention, unlisted character/object/location, and unsupported source facts.

## References

- docs/how-to-run.md
- docs/implementation/immersive-ride-entrypoint.md
- docs/data-contracts.md

