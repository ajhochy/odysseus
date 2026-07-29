---
date: 2026-07-29
repo: odysseus
tags: [decision, odysseus]
index: "[[Odysseus]]"
---

# Anthropic subscription model inventory

## Context

A static subscription catalog aged out: it omitted current models and exposed
IDs that returned model-not-found responses. API-key discovery could not repair
the list because subscription endpoints intentionally store no plaintext API
key.

## Decision

Resolve the owner-scoped encrypted OAuth session to a request-local credential
and use Anthropic's ordered, paginated `/v1/models` response as the
subscription endpoint's authoritative inventory. A successful refresh replaces
the cache and removes pinned/hidden subscription preferences for IDs no longer
available. A failed refresh retains the last known-good cache.

## Alternatives considered

- Periodically update a hard-coded catalog: rejected because it inevitably
  becomes stale between Odysseus releases.
- Fall back to the generic Anthropic API-key list during refresh: rejected
  because it is not account-scoped and already produced invalid choices.
- Prune unavailable pins for every API provider: rejected because other
  providers may intentionally use deployment IDs omitted from `/v1/models`.

## Consequences

The picker follows the connected account's actual entitlements and provider
ordering. Discovery now depends on an experimental external OAuth surface, so
failure must be non-destructive and the small curated list remains limited to
initial provisioning when no prior cache exists.
