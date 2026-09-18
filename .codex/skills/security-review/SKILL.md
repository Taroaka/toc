---
name: security-review
description: Review security-sensitive changes to authentication, authorization, untrusted inputs, secrets, payments, or data access; also use for an explicit security audit.
---

# Security Review

Identify the changed trust boundary, affected users/data, and relevant entry points. Trace concrete input-to-effect paths; review only categories that apply to the request.

| Changed boundary | Check |
| --- | --- |
| Authentication / sessions | Identity verification, expiry, session handling, and cookie/token protections appropriate to the actual authentication design. |
| Authorization / data access | Server-side ownership and tenant checks on each sensitive operation, including alternate paths and database policies where used. |
| Input / files / URLs | Schema and size limits; path containment, allowed destinations, and file content checks where relevant. Follow data through parsers, shell calls, rendering, queries, and outbound requests. |
| SQL / commands / HTML | Parameterization or safe argument passing; context-appropriate encoding/sanitization; no trust gained from a client-side check. |
| Secrets / logs / errors | No credentials or sensitive payloads in source, responses, or diagnostics. Use the environment's existing secret store. |
| Payments / writes / jobs | Authorization, replay protection or idempotency, concurrency, and bounded retries where the operation requires them. |
| Browser state changes | CSRF, CORS, and content policies matched to the actual session and deployment model. |
| Dependencies | Check advisories for changed or implicated packages; evaluate reachability and remediation instead of requiring unrelated upgrades. |

Support each finding with a file/line or function, a plausible failure or abuse path, impact, and a focused correction. Separate confirmed findings from untested hypotheses. Report no findings when the evidence supports that result.

For a review-only request, report findings. For an authorized fix, implement the relevant correction and verify the exposed behavior. Stop when the requested review/fixes and applicable checks are complete; do not turn an ordinary change into an unrelated deployment audit.
