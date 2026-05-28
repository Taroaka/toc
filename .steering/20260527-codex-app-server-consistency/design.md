# Codex App-Server Consistency Design

## Runtime Boundary

`server/codex_app_server.py` remains the only place that resolves the Codex
binary, effective `CODEX_HOME`, generated image root, network/proxy settings,
and transport diagnostics. Callers use the shared factory.

## Frontend Create Path

The create endpoint must not call `CodexAppServerClient.run_skill()` for the
main p680 generation path. The backend already owns the server process,
filesystem, and canonical environment, so it should spawn
`scripts/toc-immersive-frontend-run.py` directly. That script can still use the
shared app-server client for semantic QA and media generation, but there is no
outer app-server sandbox around it.

The `toc-immersive-runner` skill remains available for manual agent use, but it
is not the server create orchestration path.

## Failure Semantics

`CODEX_HOME` setup failures, DNS failures, backend stream disconnects, and turn
timeouts all block runtime transport. They are distinct from semantic QA
failures:

- no semantic report -> no producer repair
- semantic report with changes requested -> producer repair loop may run
- transport failure during repair -> loop becomes `blocked_transport`
- producer repair report says `status: done` but app-server turn completion
  notification times out -> accept the report and continue to rereview
- app-server turn timeout is a total deadline, not an idle-notification
  timeout

## State Contract

Runtime failures write:

- `runtime.app_server.transport.status=failed`
- `runtime.app_server.transport.error_kind=<kind>`
- `review.semantic.<stage>.transport.status=failed` when stage-scoped
- `review.semantic.<stage>.loop.status=blocked_transport`

Semantic repair writes `review.semantic.<stage>.repair.status=in_progress`
while a producer is fixing actual semantic findings, and writes
`blocked_transport` if the repair agent cannot run.
