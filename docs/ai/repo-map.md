# Repository Map

- `app.py` — FastAPI application assembly and router registration.
- `core/` — database, configuration, authentication, and shared infrastructure.
- `routes/` — HTTP endpoints, including provider setup routes.
- `src/` — LLM transports, provider resolution, and OAuth helpers.
- `static/` — browser UI and provider setup flows.
- `tests/` — Python and Node-driven regression coverage.
- `scripts/` — maintenance and workflow helpers.
- `docs/` — user and developer documentation.
- `data/`, `.env`, logs, caches — local/generated; never commit secrets or data.

Useful searches: `ProviderAuthSession`, `ModelEndpoint`, `chatgpt-subscription`,
`_build_anthropic_headers`, `resolve_session_auth`, `data-auth-flow`.
