# Project State

## Current focus

Prepare the Anthropic subscription OAuth model-inventory repair for human
review. The connected account now supplies its model catalog dynamically, and
all models exposed by that catalog have been exercised through Odysseus.

## Active branch / PR

- Branch: `workflow/run-2026-07-28-anthropic-oauth`
- Fork target: `ajhochy/odysseus`
- PR: none; merge decisions remain with a human reviewer.

## In progress

- Final commit, fork push, and fork CI inspection.

## Risks / known issues

- Anthropic subscription OAuth remains an experimental compatibility surface
  and may change independently of Odysseus.
- The original broader live criterion still lacks a real Anthropic API-key
  control account; the unchanged API-key path is covered by the complete
  repository suite.
- On macOS, the full suite must use `TMPDIR=/private/tmp` so Unix socket paths
  stay short and `/tmp` does not diverge from its canonical `/private/tmp`
  identity.

## Test status

- Static Python compilation and JavaScript syntax checks passed.
- Focused OAuth/catalog suites: 254 passed.
- Acceptance c10/c11: 2 passed.
- Issue and PR gates: 4,800 passed, 4 skipped each.
- Fresh-server probes: `/api/health` healthy; redacted subscription status
  connected with 11 provider-advertised models.
- Gated live test refreshed the catalog, matched endpoint state, and received a
  non-empty real stream from every advertised model without a 404 or safe error
  event.
- Original OAuth UI evidence: [provider setup](evidence/anthropic-subscription-setup.png)
  and [connected admin state](evidence/anthropic-subscription-admin.png).

## Next step

Commit and push the branch to the fork, inspect any triggered fork CI, then
hand the branch to a human reviewer without merging it.
