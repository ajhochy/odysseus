# Current Plan — Anthropic Subscription OAuth

## Goal

Let an Odysseus user connect an eligible Claude subscription with OAuth, select
a supported Claude model, and receive a streamed response without entering an
Anthropic API key, while preserving the existing API-key flow byte-for-byte.

## Clarification interview

Skipped at the user's direction: the observable end-to-end outcome, security
boundaries, compatibility constraints, and live-test requirement are concrete.

## Intent and constraints

- **In scope:** Claude PKCE authorization with pasted callback code; encrypted,
  owner-scoped token storage; serialized rotating refresh; an authenticated
  provider model inventory with a last-good cache; runtime resolution; OAuth-specific Anthropic headers and
  message/tool shaping; admin and `/setup` connect/reconnect/disconnect UX;
  focused, full-suite, and live inference verification.
- **Out of scope:** multi-account rotation, importing credentials without
  explicit user action, changing Anthropic API-key endpoints, adding an
  implicit 1M-context beta, bypassing plan/quota restrictions, or treating an
  undocumented compatibility flow as an official Anthropic integration.
- **Hard constraints:** reuse `ProviderAuthSession` + `ModelEndpoint`; keep
  provider credentials encrypted and owner-isolated; never persist a bearer in
  plaintext session headers, browser storage, logs, fixtures, or Git; use a
  distinct `anthropic-subscription`/OAuth auth mode; persist a rotated refresh
  token before releasing it to callers; require a deliberate live smoke before
  claiming end-to-end success.
- **Design tension:** maximize compatibility with Claude's current OAuth client
  behavior without coupling the API-key path to an undocumented surface that
  may change. Keep OAuth-specific behavior narrowly isolated and covered by
  request-shape tests.
- **Cheapest proof:** connect one owner with PKCE, refresh its authenticated
  provider inventory, then send a minimal streamed prompt through every
  advertised model. Reconnect/disconnect and failure UX follow the same
  owner-scoped boundary.

## Prior art

- Borrow from Rhythm's OpenCode Anthropic plugin: Claude PKCE authorization at
  `https://claude.ai/oauth/authorize`, exchange/refresh at
  `https://claude.ai/v1/oauth/token`, client ID
  `9d1c250a-e61b-44d9-88ed-5944d1962f5e`, pasted-code callback handling,
  per-attempt state/verifier, rotating tokens, OAuth bearer/beta headers,
  Claude-compatible system/tool transforms, and distinct auth-versus-quota
  errors.
- Borrow the independently matching Hermes safeguards: state and verifier are
  separate, refresh at least 60 seconds before expiry, never confuse
  `Authorization: Bearer` with `x-api-key`, use a curated model catalog, and do
  not silently opt requests into a 1M-context beta.
- Reuse Odysseus's ChatGPT Subscription seams: owner-scoped
  `ProviderAuthSession`, endpoint provisioning, request-time credential
  resolution, non-persistence of bearer headers, setup-route registration, and
  admin/slash-command UI conventions.
- Avoid copying a generic device-poll assumption: Claude uses an authorization
  URL plus pasted callback code, and each pending attempt must be single-use,
  owner-bound, expiring, and state-validated.

## Atomic issues

| Order | Title | Goal | Likely files | Tests / evaluation | Dependencies |
| --- | --- | --- | --- | --- | --- |
| 1 | Lock the Anthropic OAuth contract | Add failing tests for PKCE/state, exchange, 60-second refresh skew, token rotation, owner isolation, error classes, and secret redaction. | `tests/test_anthropic_subscription.py`, `tests/test_anthropic_subscription_routes.py`, `tests/test_resolve_session_auth_anthropic.py` | Tests fail only for the missing feature; fixtures contain synthetic tokens only. | None |
| 2 | Add the owner-scoped OAuth service and setup routes | Implement authorization start/complete/status/disconnect, encrypted auth-session upsert, curated models, endpoint provisioning, reconnect, and serialized refresh. | `src/anthropic_subscription.py`, `routes/anthropic_subscription_routes.py`, `app.py`, `core/database.py` only if the existing schema proves insufficient | Issue 1 service/route tests; malformed, expired, replayed, wrong-owner, denied, 401/403, and 429 cases. | 1 |
| 3 | Separate OAuth runtime transport from API-key Anthropic | Resolve the auth session at request time, preserve OAuth bearer auth, add only required OAuth betas/transforms, keep tokens request-local, and leave API-key headers/payloads unchanged. | `src/endpoint_resolver.py`, `routes/chat_helpers.py`, `routes/model_routes.py`, `src/llm_core.py` | Header/payload snapshots for both auth modes; concurrency/rotation; authenticated model inventory with last-good retention; sync and streamed chat regressions. | 2 |
| 4 | Wire connect, reconnect, and disconnect UX | Add Anthropic Subscription to admin and `/setup`, open the authorize URL, accept pasted callback input, show status/errors, refresh models, and expose reconnect/disconnect without displaying secrets. | `static/index.html`, `static/js/admin.js`, `static/js/slashCommands.js`, a small shared OAuth helper under `static/js/` if useful | Node DOM-free flow tests plus static wiring tests for success, cancel, invalid paste, expiry, retry, reconnect, and disconnect. | 2 |
| 5 | Verify the full compatibility path | Run focused and full regression checks, then perform a deliberate Claude login/refresh/stream smoke and record evidence without credentials. | Test files above; `docs/ai/project-state.md` only after verified implementation | Compile, Python suite, JS syntax/tests, health check, OAuth connect, non-empty streamed response, forced/near-expiry refresh, API-key control request. | 3, 4 |

## Acceptance criteria

1. From Admin or `/setup anthropic-subscription`, an authenticated user starts
   a connection and sees an Anthropic authorization URL. Completing Claude
   login and pasting the returned code creates or reconnects exactly that
   owner's enabled endpoint and makes the curated Claude models selectable;
   cancel, expiry, malformed paste, state mismatch, and replay leave stored
   credentials unchanged and show a safe retryable error.
2. Two simultaneous or sequential pending attempts have distinct state and
   verifier values, are owner-bound and single-use, and cannot complete one
   another's flow. A second user cannot view, resolve, reconnect, or disconnect
   the first user's auth session or endpoint.
3. When a linked access token expires within 60 seconds, concurrent requests
   perform one refresh per auth session. A returned rotated refresh token and
   access token are committed together before any caller proceeds; refresh
   failure preserves a recoverable state and invalid/missing credentials
   produce a reconnect-required response.
4. A request through an Anthropic subscription endpoint sends
   `Authorization: Bearer`, `anthropic-version`, and only the OAuth beta headers
   required by the validated prior-art contract; it never sends `x-api-key`.
   The same request through an Anthropic API-key endpoint still sends
   `x-api-key`, does not gain OAuth-only betas/transforms, and passes its
   existing regression tests unchanged.
5. OAuth requests apply the validated Claude system-prompt and tool
   transformations in sync and streaming paths, while preserving normal
   assistant text/tool behavior. No code path adds a 1M-context beta unless a
   future explicit setting and test opt into it.
6. OAuth 401/403 or invalid-grant responses tell the user to reconnect; 429
   responses identify quota/rate limiting without claiming credentials are
   invalid; denial, upstream, and network failures remain distinct and do not
   log response bodies or tokens.
7. Disconnect removes only the caller's endpoint/auth reference, clears its
   models from selection, and leaves other owners and API-key Anthropic
   endpoints untouched. Reconnect replaces credentials for the same owner
   without creating duplicate active endpoints.
8. Access tokens, refresh tokens, authorization codes, PKCE verifiers, and
   state values never appear in application logs, plaintext session headers,
   browser storage, committed fixtures, or API responses; persisted tokens use
   `EncryptedText`.
9. End-to-end success is claimed only after a local app health check, an
   interactive OAuth completion (or an explicitly existing local Claude
   login), a normal Odysseus chat producing a non-empty streamed Claude
   response, a refresh-path smoke, and a control request proving an Anthropic
   API key still works. If no eligible local login or interactive approval is
   available, report the live smoke as blocked—not passed.

## Policy, compatibility, and safety

Claude subscription OAuth is an external compatibility surface and may change
or be restricted by Anthropic policy. Present it as opt-in/experimental, honor
account entitlements and quota responses, keep endpoints/client constants
isolated for review, and do not imply official support. Live testing must use
the user's already authorized local account or their interactive approval;
never solicit, print, export, or commit credentials.

## Known ambiguities

None that block implementation. Exact OAuth beta names and system/tool
transform details must be copied from and snapshot-tested against the validated
Rhythm/Hermes contract at implementation time, not guessed from generic
Anthropic API behavior.
