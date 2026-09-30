# Architecture

Odysseus is a FastAPI self-hosted workspace with a static browser client.
Model endpoints are stored in the database. API-key endpoints keep their key
on the endpoint; subscription providers keep refreshable credentials in an
owner-scoped `ProviderAuthSession` referenced by the endpoint.

Chat requests resolve endpoint credentials at request time, then `src/llm_core.py`
normalizes messages and dispatches to provider-specific HTTP transports.
Provider setup routes provision both the auth session and model endpoint.

External dependencies for this feature are Anthropic's authorization/token
services, the Anthropic Messages API, and optionally Claude Code's local
credential store.
