# Preapproved Review Mode Design

## Contract

`review_mode` は `standard | preapproved`。既定は `standard`。

経路:

1. frontend が create API に `review_mode` を送る。
2. backend が job と CLI `--review-mode` に伝播する。
3. runner が create_input.json と state.txt に保存する。
4. semantic review entrypoint は `preapproved` の場合も canonical pack/digest を作るが、Codex reviewer turn は起動しない。
5. orchestrator が全 entry を reviewed とする digest-bound report を生成する。
6. 通常の semantic checker、P400/P650/P680 validator、画像生成経路をそのまま通す。
7. P680 handoff は `review.image.status=approved`、`slot.p680.status=done` とする。

## Safety Boundary

preapproved が省略するのは判断主体としての review process のみ。以下は維持する。

- run-root / no-follow binding
- YAML/JSON/schema validation
- source/request digest binding
- asset/reference existence and hashes
- provider output provenance
- generated image decoding/existence
- fixed-slot and artifact completeness

## Evidence

- semantic report `notes` と state に `preapproved` / `deterministic_preapproval` を保存する。
- app-server debug log に reviewer bypass を記録する。

