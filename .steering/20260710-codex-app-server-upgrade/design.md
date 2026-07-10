# Codex app-server upgrade design

## Decision

Keep every active caller on `create_codex_app_server_client()` and strengthen that single boundary:

1. Detect `codex --version` during preflight.
2. Require at least `0.144.0` by default.
3. Send `gpt-5.6-sol` explicitly on every `thread/start` unless the dedicated ToC environment variable overrides it.
4. Include the effective version/model contract in diagnostics.

## Rationale

The app-server is shipped with the Codex CLI, so upgrading the CLI upgrades the server implementation and generated protocol schema together. The current request/notification shapes used by ToC remain compatible with `0.144.0`; per-call-site protocol rewrites would duplicate policy and increase drift.

An explicit ToC model default prevents frontend and background-agent behavior from depending on a developer's global `$CODEX_HOME/config.toml`. The environment override remains available for controlled rollback or evaluation.

## Compatibility

- Keep stdio JSONL transport and the existing `initialize`/`initialized` handshake.
- Keep `experimentalApi: true` because active skills and image-generation items depend on that app-server surface.
- Keep `thread/start` and `turn/start` request shapes unchanged apart from always supplying the effective model.
- Parse semantic versions from `codex-cli X.Y.Z`, preserve prerelease/build suffixes, reject a matching-core prerelease against a stable minimum, and ignore build metadata for precedence.

## Failure behavior

- Missing CLI: existing `codex executable not found` failure.
- Unparseable version: fail preflight with the raw version output in diagnostics.
- CLI below minimum: fail preflight before starting app-server, with upgrade guidance.
- Explicit unsupported model: app-server returns its normal model error; the requested effective model is visible in diagnostics.

## Verification

- Unit tests for default and overridden model selection.
- Unit tests for version parsing, override, accepted current version, and rejected old version.
- Existing app-server/image/server regression tests.
- Real `model/list` plus a no-op `thread/start`/`turn/start` using `gpt-5.6-sol`.
