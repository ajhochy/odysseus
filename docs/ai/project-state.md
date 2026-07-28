# Project State

## Current focus

Add owner-scoped Anthropic subscription OAuth support without weakening the
existing Anthropic API-key path.

## Branch

`workflow/run-2026-07-28-anthropic-oauth`, based on freshly fetched
`origin/dev` at `25a4d13`.

## Known risks

- Anthropic subscription OAuth is a compatibility surface that may change.
- Refresh tokens rotate and must be persisted atomically.
- OAuth requests require different headers and request shaping from API-key
  requests.

## Test status

Baseline checks pending.

## Next step

Write the acceptance contract and focused failing tests, then implement.

## Recent coding-agent runs

### 2026-07-28 — issue-0-anthropic-subscription-oauth
- Files modified: `src/anthropic_subscription.py` (PKCE, exchange/refresh, headers, transforms, errors), `routes/anthropic_subscription_routes.py` (owner-scoped connect/status/disconnect and endpoint provisioning), `core/database.py` (encrypted auth expiry metadata), `src/endpoint_resolver.py`, `routes/chat_helpers.py`, `routes/model_routes.py`, `src/llm_core.py`, and `app.py` (runtime/transport/route wiring); focused Python tests; UI files were modified by the parallel UI worker.
- Checks run: required baseline contracts failed as expected (Python 9 failed; Node 1 failed); focused Anthropic OAuth tests passed (21); adjacent ChatGPT Subscription, Anthropic, endpoint resolver, model-route, and streaming regressions passed (278). The required final contract rerun is the last handoff action.
- Decisions made: minimal Odysseus-specific OAuth transforms, static no-probe model catalog, explicit token expiry, and request-local auth-mode metadata; see `docs/ai/decisions.md`.
- Deviations from spec: none.
- Concerns: Anthropic subscription OAuth remains an undocumented, opt-in compatibility surface; live account authorization, refresh, streamed inference, and API-key control smoke remain intentionally account-gated for the orchestrator.
