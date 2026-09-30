# Architecture Decisions

## 2026-07-28 — Separate Anthropic subscription authentication mode

Anthropic API keys and subscription OAuth share the Messages API payload
adapter but use separate endpoint/authentication modes. This prevents OAuth
bearer tokens from being rewritten as `x-api-key` values and makes credential
refresh and reconnect state explicit.

## 2026-07-28 — Reuse the provider auth-session boundary

Store owner-scoped access/refresh state in `ProviderAuthSession` and reference
it from `ModelEndpoint`, following the ChatGPT Subscription design. Refresh
tokens rotate, so refresh is serialized and the replacement token is committed
before returning an access token to callers.

## 2026-07-28 — Keep Claude OAuth compatibility transforms minimal

Odysseus applies only the validated compatibility pieces its existing
Anthropic Messages adapter needs: Claude Code identity isolation, relocation of
the application's system prompt into the first user turn, `mcp_`/PascalCase
tool names on the OAuth wire, and reversal of that prefix on streamed tool
calls. Rhythm's dynamic billing-header signing, account rotation, OpenCode
response proxy, and model-specific beta fallback machinery remain
OpenCode-specific and were not copied.

OAuth requests use the shared Hermes/Rhythm bearer fingerprint (Claude/OAuth
plus established stream/thinking betas) without the 1M-context beta. Models
come from a curated static catalog and are never discovered by probing with a
subscription bearer.

## 2026-07-28 — Carry auth mode as request-local credential metadata

The existing endpoint resolver API returns `(base_url, api_key)` and has many
callers. A `str` subclass carries `auth_mode` in memory so those callers remain
compatible while header construction can distinguish Anthropic OAuth bearer
transport from `x-api-key`. The value serializes as an ordinary string only if
a caller explicitly serializes it; subscription session paths instead clear
plaintext persisted headers and resolve a new credential on every request.

`ProviderAuthSession.expires_at` records token expiry explicitly because
Anthropic access tokens are not assumed to be JWTs. The startup migration adds
the nullable column for existing databases.

## 2026-07-29 — Discover subscription models at the OAuth boundary

The live account proved that a static subscription catalog becomes stale and
can advertise model IDs that return HTTP 404. Subscription refresh now resolves
the owner-scoped `ProviderAuthSession` to a request-local `RuntimeCredential`
and fetches Anthropic's ordered `/v1/models` inventory with the established
OAuth header fingerprint.

The small curated list remains only as an emergency initial-provisioning
fallback. It never replaces a provider inventory during refresh: successful
discovery replaces `cached_models`, while failed or empty discovery retains the
last known-good cache. Anthropic API-key discovery remains unchanged.
