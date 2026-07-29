# Follow-up: Anthropic subscription catalog advertises stale or invalid models

Status: resolved locally on `workflow/run-2026-07-28-anthropic-oauth`.

## Failure

The live OAuth connection succeeded, but the connected endpoint exposed old
model IDs and some selectable entries returned HTTP 404.

## Repro

Connect an Anthropic subscription in the isolated local app, enumerate the
models advertised for that endpoint, and send a minimal streamed request
through each model.

## Expected

The endpoint advertises the current subscription-compatible Claude models, and
every advertised model completes a minimal request without a model-not-found
response.

## Required fix

Replace or refresh the static catalog at the authenticated provider boundary,
preserve owner scoping and encrypted token handling, and synchronize existing
connected endpoints without requiring credentials to be re-entered.

## Required validation

- Focused catalog/provisioning regression test.
- Live minimal streamed request through every advertised model.
- Existing Anthropic API-key regression tests.

## Verification evidence

- Authenticated refresh returned Anthropic's ordered 11-model inventory and
  removed retired pinned/hidden IDs from the connected subscription endpoint.
- `ODYSSEUS_ANTHROPIC_LIVE=1
  ODYSSEUS_LIVE_BASE_URL=http://127.0.0.1:7148 .venv/bin/python -m pytest -q
  tests/live/test_anthropic_subscription_live.py -s` exercised every advertised
  model through the real session and chat-stream routes: 1 test passed, with no
  HTTP 404, safe error event, or empty streamed response.
- `TMPDIR=/private/tmp ai-workflow checks --level issue`: 4,800 passed, 4
  skipped.
- `TMPDIR=/private/tmp ai-workflow checks --level pr`: 4,800 passed, 4 skipped,
  including Python compilation and JavaScript syntax checks.

## Acceptance Criteria

1. An authenticated Anthropic subscription model refresh uses the owner-scoped
   OAuth bearer and OAuth headers to return the provider's ordered `/v1/models`
   inventory; it never substitutes Odysseus's generic Anthropic API-key
   fallback list.
2. Existing connected subscription endpoints adopt a successful refreshed
   inventory without reauthorization, and a failed refresh retains the last
   known-good cache.
3. Every model advertised after refresh completes a minimal live streamed
   request without HTTP 404 or an empty response.
