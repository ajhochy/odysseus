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

- Static Python and JavaScript checks are green at commit `33ea46b`.
- Focused OAuth contract/runtime checks: 30 Python tests and 6 Node tests
  green.
- Repository regression run: 4,792 passed, 4 skipped, with the single
  unchanged macOS `/tmp` alias baseline test deselected and documented at
  `docs/ai/issues/followup-macos-tmp-alias.md`.
- Isolated app `/api/health` and `/api/ready` returned healthy/ready.
- Admin and `/setup anthropic-subscription` were exercised in the live UI and
  reached Anthropic's real signed-in consent page.
- End-to-end callback, refresh, and inference remain blocked by Anthropic's
  hCaptcha. No live-success claim has been made; see
  `docs/ai/issues/followup-anthropic-live-captcha.md`.

## Next step

Complete the visible Anthropic CAPTCHA, paste the returned callback into the
preserved Odysseus setup tab, then run the gated live test:

```bash
ODYSSEUS_ANTHROPIC_LIVE=1 \
ODYSSEUS_LIVE_BASE_URL=http://127.0.0.1:7147 \
.venv/bin/python -m pytest -q \
  tests/live/test_anthropic_subscription_live.py
```

## Recent coding-agent runs

### 2026-07-28 — issue-0-anthropic-subscription-oauth
- Files modified: `src/anthropic_subscription.py` (PKCE, exchange/refresh, headers, transforms, errors), `routes/anthropic_subscription_routes.py` (owner-scoped connect/status/disconnect and endpoint provisioning), `core/database.py` (encrypted auth expiry metadata), `src/endpoint_resolver.py`, `routes/chat_helpers.py`, `routes/model_routes.py`, `src/llm_core.py`, and `app.py` (runtime/transport/route wiring); focused Python tests; UI files were modified by the parallel UI worker.
- Checks run: required baseline contracts failed as expected (Python 9 failed; Node 1 failed); focused Anthropic OAuth tests passed (21); adjacent ChatGPT Subscription, Anthropic, endpoint resolver, model-route, and streaming regressions passed (278). The required final contract rerun is the last handoff action.
- Decisions made: minimal Odysseus-specific OAuth transforms, static no-probe model catalog, explicit token expiry, and request-local auth-mode metadata; see `docs/ai/decisions.md`.
- Deviations from spec: none.
- Concerns: Anthropic subscription OAuth remains an undocumented, opt-in compatibility surface; live account authorization, refresh, streamed inference, and API-key control smoke remain intentionally account-gated for the orchestrator.
