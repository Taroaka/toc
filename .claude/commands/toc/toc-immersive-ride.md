# /toc-immersive-ride

ToC の没入型 cinematic story run を topic/source から作る command。

## 使い方

```text
/toc-immersive-ride --topic "桃太郎"
/toc-immersive-ride --topic "自由意志" --experience cloud_island_walk
/toc-immersive-ride --topic "桃太郎" --stage p300
```

## Experiences

- `cinematic_story`: scene intent に応じた POV/三人称。1 cut 内は視点を固定する。
- `cloud_island_walk`: 雲上の島、道/階段/橋、物理 metaphor を使って概念を示す。
- `world_walk`: existing run の asset を観察者 POV で歩き、source character は遠景で扱う。
- `ride_action_boat`: legacy alias、内部では `cinematic_story`。

共通で実写 cinematic、画面内 text/logo/watermark なし、stable character/object/location
references、1 cut 1 primary intent を使う。

## Arguments

```text
--topic <topic>                         required
--source-run output/<run>               required for world_walk
--stage research|story|visual_value|script|asset|scene_implementation|narration|video_generation|render|video
--experience cinematic_story|cloud_island_walk|world_walk|ride_action_boat
--video-tool kling|kling-omni|seedance|veo
--dry-run
```

Coarse stage targets resolve to active slots:

```text
p100→p120  p200→p220  p300→p330  p400→p450  p500→p570
p600→p680  p700→p750  p800→p840  p900→p920
```

p400 authoring creates scene/cut contracts and skeleton manifest. p500 asset, p600 image, p700
narration, p800 video, and p900 render follow.

## Execution flow

```text
source context
  → research.md
  → story.md
  → visual_value.md
  → script.md + video_manifest.md (skeleton)
  → asset plan/request/output
  → image request/output
  → narration/TTS and measured duration
  → motion request/output
  → normalized render and ordinary QA
```

Use `prepare-stage-context.py` for required docs/templates/inputs and read the returned readset in
`global_docs → stage_docs → templates → inputs` order. Before each provider call validate schema,
types, IDs, references, request snapshot, hashes, file/decode, duration, streams, and provenance.

## Output

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

## Optional user actions

Candidate selection, listening, image/narration editing, and change requests are optional. Store each
choice with actor, timestamp, selectors, and request revision, then rerun ordinary checks.
Hybridization of contradictory source variants and publication are separate explicit user actions.

