---
name: backend-patterns
description: Choose API, service, persistence, or job patterns when designing or changing Node.js/Express/Next.js backend behavior.
---

# Backend Patterns

Start from the existing service boundaries and contracts. Add a repository layer, queue, cache, or middleware only when the requested behavior needs it. Examples are illustrative; use the installed library APIs and production storage/authentication mechanisms.

Read only the part relevant to the change:

- [API boundaries](references/api-boundaries.md): routes, repositories, services, and middleware.
- [Data and caching](references/data-caching.md): query shape, N+1 calls, transactions, and cache invalidation.
- [Operations](references/operations.md): errors, retries, authorization, rate limits, queues, and logging.

Preserve existing response contracts. Define retry behavior around idempotency and the actual failure: do not retry a non-idempotent write blindly. In-memory queue and rate-limit examples are process-local and do not provide durable or cross-worker guarantees.

Verify the changed boundary and its failure behavior with the repo's existing checks. For another stack, use its native implementation and docs instead of translating these examples by default.
