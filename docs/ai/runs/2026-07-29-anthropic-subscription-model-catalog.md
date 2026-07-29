---
date: 2026-07-29
repo: odysseus
branch: workflow/run-2026-07-28-anthropic-oauth
pr: null
issues:
  - local-followup-anthropic-model-catalog
status: verified
tags: [run, odysseus]
index: "[[Odysseus]]"
---

# Anthropic subscription model catalog

## Files changed

- `src/anthropic_subscription.py`: authenticated, paginated provider inventory
  discovery and a current emergency-only fallback.
- `routes/anthropic_subscription_routes.py`: live inventory provisioning,
  last-good retention, and removal of unavailable subscription preferences.
- `routes/model_routes.py`: owner-scoped OAuth credentials for every refresh
  path, real OAuth model probes, and subscription-only stale preference
  pruning.
- Contract, focused, and gated live tests under `tests/`.
- Acceptance, decision, failure-pattern, and project-state documentation.

## Checks run

- Python compilation and JavaScript syntax checks: passed.
- Focused OAuth/catalog suites: 254 passed.
- Acceptance c10/c11: 2 passed.
- `TMPDIR=/private/tmp ai-workflow checks --level issue`: 4,800 passed, 4
  skipped.
- `TMPDIR=/private/tmp ai-workflow checks --level pr`: 4,800 passed, 4 skipped.
- Fresh-server health and redacted subscription-status probes: healthy and
  connected.
- Gated live refresh and session/chat-stream test: every one of the 11
  provider-advertised models returned a non-empty stream with no 404 or safe
  error event.

## Notes

- Decision: Anthropic's authenticated `/v1/models` response is authoritative
  for subscription endpoints. Failed discovery retains the last good cache;
  the curated list is only for first-provisioning emergencies.
- Failure triage: the first user smoke exposed stale hard-coded IDs. The first
  live regression then exposed legacy pinned IDs being merged back after a
  good refresh. The initial all-model test also over-constrained model wording;
  transport/authentication assertions were retained while the unrelated phrase
  match was removed.
- Gate recovery: restricted local sockets/DNS caused false failures; the
  unrestricted suite reduced these to macOS temp-path artifacts and
  unreferenced screenshots. The screenshots were linked as evidence, and the
  canonical short temp root made all repository checks green.
- Follow-up: `docs/ai/issues/followup-anthropic-model-catalog.md` is resolved.
  The broader API-key live-control criterion remains explicitly pending.
