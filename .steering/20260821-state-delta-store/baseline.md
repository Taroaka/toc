# Baseline: legacy Cinderella state

Measured after the prior resume process ended, before migrating that run:

- run: `output/シンデレラ_20260812_2341`
- `state.txt`: 449,600,344 bytes
- lines: 6,079,595
- committed legacy blocks: 6,933
- file modified: `2026-08-21T00:20:51+0900`
- one sequential `wc` + delimiter scan: 2.26 s wall / 1.44 s user / 0.25 s sys
- new streaming legacy reducer on the full file: 8.81 s wall / 7.29 s user /
  0.52 s sys; 1,104 current keys, no incomplete tail
- derived current view for those 1,104 keys: 89,864 bytes; 1,000 validated
  parses in 2.503 s, or 2.503 ms mean per parse

The legacy writer also copied and appended a complete current mapping for each
update, so its update cost included both the full-history read and a full-file
COW publication. The delta writer instead appends one changed-key record in
place; the one-time migration read for this run is about 8.8 seconds, after
which reads and writes use
`state.current.json` and do not scan these 449.6 MB again.

For the state-read component alone, the measured warm path is roughly 3,500x
faster than replaying this legacy history (8.81 s versus 2.503 ms). This does
not include provider/semantic-review time or derived index rendering.

This file records evidence only. The Cinderella canonical state bytes were not
modified by the measurement.
