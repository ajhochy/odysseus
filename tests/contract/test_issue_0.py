"""Executable acceptance contract for issue 0: Anthropic Subscription OAuth.

The feature is deliberately absent when this contract is introduced.  These
tests inspect the real application surfaces (rather than importing a missing
module) so the initial red run reports missing behavior as assertions, not as
collection/import errors.  All credential-looking values below are inert,
synthetic markers; no test makes a network request.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _source(relative_path: str) -> str:
    """Load a required production surface with an assertion-rich failure."""
    path = ROOT / relative_path
    assert path.is_file(), (
        f"Missing {relative_path}: Anthropic Subscription OAuth has not been "
        "implemented yet (contract failure, not a test setup/import error)."
    )
    return path.read_text(encoding="utf-8")


def _require_all(text: str, *needles: str) -> None:
    missing = [needle for needle in needles if needle not in text]
    assert not missing, f"Missing required Anthropic Subscription wiring: {missing}"


def test_issue_0_c1_authorize_complete_and_safe_retry_wiring():
    """Regression: a failed/replayed callback must never replace stored credentials."""
    service = _source("src/anthropic_subscription.py")
    routes = _source("routes/anthropic_subscription_routes.py")
    admin_js = _source("static/js/admin.js")
    slash_js = _source("static/js/slashCommands.js")

    _require_all(
        service,
        "ANTHROPIC_SUBSCRIPTION_PROVIDER",
        "https://claude.ai/oauth/authorize",
        "exchange_authorization_code",
        "authorization_code",
        "code_verifier",
        "state",
    )
    _require_all(
        routes,
        "setup_anthropic_subscription_routes",
        "start",
        "complete",
        "disconnect",
        "expires",
    )
    _require_all(admin_js, "anthropic-subscription")
    _require_all(slash_js, "anthropic-subscription")


def test_issue_0_c2_pending_attempts_and_resources_are_owner_scoped():
    """Regression: Alice can submit Bob's state or access Bob's endpoint/session."""
    service = _source("src/anthropic_subscription.py")
    routes = _source("routes/anthropic_subscription_routes.py")

    _require_all(
        service,
        "PendingAuthorization",
        "owner",
        "state",
        "code_verifier",
        "single-use",
        "replay",
    )
    _require_all(
        routes,
        "ProviderAuthSession.owner == owner",
        "ModelEndpoint.owner == owner",
        "owner",
    )


def test_issue_0_c3_refresh_is_serialized_at_60_seconds_and_commits_rotation():
    """Regression: simultaneous expired requests refresh twice or expose an uncommitted rotated token."""
    service = _source("src/anthropic_subscription.py")

    _require_all(
        service,
        "ANTHROPIC_ACCESS_TOKEN_REFRESH_SKEW_SECONDS = 60",
        "threading.Lock",
        "refresh_oauth_tokens",
        "row.access_token",
        "row.refresh_token",
        "db.commit()",
        "Reconnect",
    )


def test_issue_0_c4_oauth_and_api_key_transport_are_separate():
    """Regression: OAuth sends x-api-key or the API-key path inherits OAuth-only headers."""
    service = _source("src/anthropic_subscription.py")
    resolver = _source("src/endpoint_resolver.py")
    llm_core = _source("src/llm_core.py")

    _require_all(
        service,
        "anthropic_subscription_headers",
        "Authorization",
        "Bearer",
        "anthropic-version",
        "x-api-key",
        "OAUTH_BETA",
    )
    _require_all(resolver, "anthropic_subscription", "resolve_runtime_credentials")
    _require_all(llm_core, "anthropic_subscription_headers", "auth_mode")


def test_issue_0_c5_oauth_message_and_tool_transforms_apply_to_both_paths():
    """Regression: stream requests bypass the OAuth Claude system/tool shaping or add a 1M beta."""
    service = _source("src/anthropic_subscription.py")
    llm_core = _source("src/llm_core.py")

    _require_all(
        service,
        "transform_oauth_messages",
        "transform_oauth_tools",
        "1m",
        "not in",
    )
    # The real sync and stream branches must both call the narrowly scoped transform.
    assert llm_core.count("transform_oauth_messages") >= 2, (
        "OAuth message transforms must be wired in both sync and streaming paths"
    )
    assert llm_core.count("transform_oauth_tools") >= 1, (
        "OAuth tool transforms must be wired before streamed Anthropic requests"
    )


def test_issue_0_c6_error_classes_preserve_reconnect_quota_and_safe_failures():
    """Regression: a 429 tells users to reconnect, or upstream response bodies/tokens reach logs."""
    service = _source("src/anthropic_subscription.py")
    routes = _source("routes/anthropic_subscription_routes.py")

    _require_all(
        service,
        "AnthropicSubscriptionReauthRequired",
        "AnthropicSubscriptionRateLimited",
        "invalid_grant",
        "status_code == 429",
        "401",
        "403",
        "Reconnect",
    )
    _require_all(routes, "to_http_exception", "429", "Reconnect")
    assert "response.text" not in service and "response.content" not in service, (
        "OAuth error mapping must not expose upstream response bodies"
    )


def test_issue_0_c7_disconnect_and_reconnect_only_change_the_callers_resources():
    """Regression: disconnect removes another owner's endpoint or reconnect duplicates an active endpoint."""
    routes = _source("routes/anthropic_subscription_routes.py")

    _require_all(
        routes,
        "_provision_endpoint",
        "ProviderAuthSession.provider",
        "ProviderAuthSession.owner == owner",
        "ModelEndpoint.owner == owner",
        "provider_auth_id",
        "is_enabled = True",
        "db.delete",
    )
    assert "filter(ModelEndpoint.owner == owner" in routes or "ModelEndpoint.owner == owner," in routes, (
        "Endpoint deletion/reconnect lookup must be owner-scoped"
    )


def test_issue_0_c8_credentials_are_encrypted_and_never_exposed_or_persisted_in_headers():
    """Regression: a bearer/code/verifier/state leaks to JSON, browser storage, logs, or plaintext sessions."""
    service = _source("src/anthropic_subscription.py")
    routes = _source("routes/anthropic_subscription_routes.py")
    database = _source("core/database.py")
    chat_helpers = _source("routes/chat_helpers.py")
    admin_js = _source("static/js/admin.js")
    slash_js = _source("static/js/slashCommands.js")
    oauth_helper_js = _source("static/js/anthropicSubscriptionFlow.js")

    _require_all(database, "class ProviderAuthSession", "access_token = Column(EncryptedText", "refresh_token = Column(EncryptedText")
    _require_all(service, "redact", "access_token", "refresh_token", "code_verifier", "state")
    _require_all(routes, "access_token", "refresh_token")
    assert (
        "is_anthropic_subscription" in chat_helpers
        and 'stale_q.update({"headers": {}})' in chat_helpers
    ), (
        "Subscription bearer must stay request-local rather than persist in session headers"
    )
    assert "localstorage" not in oauth_helper_js.lower(), (
        "Anthropic Subscription OAuth helper must not write credentials to browser storage"
    )


def test_issue_0_health_wiring_exists_before_manual_live_smoke():
    """Automatable support for criterion 9; real OAuth/inference remains manual and account-gated."""
    app = _source("app.py")
    routes = _source("routes/anthropic_subscription_routes.py")
    health = _source("src/service_health.py")

    _require_all(app, "setup_anthropic_subscription_routes", "include_router")
    _require_all(routes, "APIRouter")
    _require_all(health, "ModelEndpoint", "is_enabled")


def test_issue_0_c10_authenticated_model_inventory_never_uses_api_key_fallback(
    monkeypatch,
):
    """Regression: OAuth refresh silently swaps in Odysseus's stale API-key list."""
    import routes.model_routes as model_routes
    from src import anthropic_subscription
    from src.endpoint_resolver import RuntimeCredential

    provider_models = [
        "claude-opus-5",
        "claude-sonnet-5",
        "claude-fable-5",
        "claude-haiku-4-5-20251001",
    ]
    observed = {}

    class ProviderResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [{"id": model} for model in provider_models]}

    def fake_get(url, *, headers, params=None, timeout=None, **kwargs):
        observed.update(
            {
                "url": url,
                "headers": headers,
                "params": params,
                "timeout": timeout,
            }
        )
        return ProviderResponse()

    monkeypatch.setattr(anthropic_subscription.httpx, "get", fake_get)
    credential = RuntimeCredential(
        "synthetic-oauth-access", "anthropic-subscription"
    )

    result = model_routes._probe_endpoint(
        "https://api.anthropic.com", credential, timeout=7
    )

    assert result == provider_models
    assert observed["url"] == "https://api.anthropic.com/v1/models"
    assert observed["headers"]["Authorization"] == (
        "Bearer synthetic-oauth-access"
    )
    assert "x-api-key" not in {
        str(key).lower() for key in observed["headers"]
    }


def test_issue_0_c11_refresh_updates_existing_cache_and_preserves_last_good_inventory(
    monkeypatch,
):
    """Regression: refresh loses auth mode or erases a good cache after discovery fails."""
    import json
    from types import SimpleNamespace

    from fastapi import Response
    import routes.model_routes as model_routes
    from src.endpoint_resolver import RuntimeCredential

    endpoint = SimpleNamespace(
        id="subscription-endpoint",
        name="Anthropic Subscription (experimental)",
        base_url="https://api.anthropic.com",
        api_key=None,
        provider_auth_id="subscription-auth",
        owner="alice",
        is_enabled=True,
        cached_models=json.dumps(["claude-sonnet-4-5"]),
        hidden_models=json.dumps(["claude-haiku-3-5"]),
        pinned_models=json.dumps(["claude-haiku-3-5"]),
        endpoint_kind="api",
        model_refresh_mode="manual",
        model_refresh_timeout=None,
    )

    class Query:
        def filter(self, *args, **kwargs):
            return self

        def first(self):
            return endpoint

    class Database:
        def query(self, model):
            return Query()

        def commit(self):
            return None

        def close(self):
            return None

    credential = RuntimeCredential(
        "synthetic-oauth-access", "anthropic-subscription"
    )
    provider_models = ["claude-opus-5", "claude-sonnet-5"]
    state = {"fail": False, "resolved": 0}

    def fake_resolve_probe_key(ep):
        assert ep is endpoint
        state["resolved"] += 1
        return credential

    def fake_probe(base, api_key, timeout):
        assert base == "https://api.anthropic.com"
        if state["fail"]:
            return []
        if getattr(api_key, "auth_mode", None) == "anthropic-subscription":
            return provider_models
        return []

    monkeypatch.setattr(model_routes, "SessionLocal", Database)
    monkeypatch.setattr(model_routes, "require_admin", lambda request: None)
    monkeypatch.setattr(model_routes, "_resolve_probe_key", fake_resolve_probe_key)
    monkeypatch.setattr(model_routes, "_probe_endpoint", fake_probe)

    router = model_routes.setup_model_routes(model_discovery=None)
    route = next(
        item.endpoint
        for item in router.routes
        if item.path == "/api/model-endpoints/{ep_id}/models"
        and "GET" in item.methods
    )

    refreshed_response = Response()
    refreshed = route(
        endpoint.id,
        object(),
        refreshed_response,
        refresh=True,
        refresh_timeout=7,
    )
    assert [item["id"] for item in refreshed] == provider_models
    assert json.loads(endpoint.cached_models) == provider_models
    assert endpoint.pinned_models is None
    assert endpoint.hidden_models is None
    assert refreshed_response.headers["X-Model-Refresh-Status"] == "refreshed"

    state["fail"] = True
    failed_response = Response()
    retained = route(
        endpoint.id,
        object(),
        failed_response,
        refresh=True,
        refresh_timeout=7,
    )
    assert [item["id"] for item in retained] == provider_models
    assert json.loads(endpoint.cached_models) == provider_models
    assert failed_response.headers["X-Model-Refresh-Status"] == "failed"
    assert state["resolved"] == 2
