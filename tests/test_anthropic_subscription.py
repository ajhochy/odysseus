"""Focused Anthropic subscription OAuth service regressions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database import Base, ProviderAuthSession
from src import anthropic_subscription as subscription


@pytest.fixture(autouse=True)
def _clear_pending():
    subscription.PENDING_AUTHORIZATIONS.clear()
    yield
    subscription.PENDING_AUTHORIZATIONS.clear()


def _state(start):
    return parse_qs(urlparse(start["authorize_url"]).query)["state"][0]


def test_pkce_attempts_are_independent_owner_bound_and_single_use():
    first = subscription.start_authorization("alice", now=100)
    second = subscription.start_authorization("alice", now=100)
    bob = subscription.start_authorization("bob", now=100)

    assert first["attempt_id"] != second["attempt_id"]
    assert _state(first) != _state(second)

    captured = []

    def exchange(**values):
        captured.append(values)
        return {
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
        }

    with pytest.raises(subscription.AnthropicSubscriptionFlowError):
        subscription.complete_authorization(
            "bob",
            first["attempt_id"],
            f"synthetic-code#{_state(first)}",
            exchange=exchange,
            now=101,
        )
    with pytest.raises(subscription.AnthropicSubscriptionFlowError):
        subscription.complete_authorization(
            "alice",
            first["attempt_id"],
            f"synthetic-code#{_state(second)}",
            exchange=exchange,
            now=101,
        )
    result = subscription.complete_authorization(
        "alice",
        first["attempt_id"],
        f"synthetic-code#{_state(first)}",
        exchange=exchange,
        now=101,
    )
    assert result["access_token"] == "synthetic-access"
    assert captured[0]["authorization_code"] == "synthetic-code"
    assert captured[0]["state"] == _state(first)
    assert captured[0]["code_verifier"] != _state(first)

    with pytest.raises(subscription.AnthropicSubscriptionFlowError, match="already used"):
        subscription.complete_authorization(
            "alice",
            first["attempt_id"],
            f"synthetic-code#{_state(first)}",
            exchange=exchange,
            now=101,
        )
    assert subscription.PENDING_AUTHORIZATIONS.has(second["attempt_id"], "alice")
    assert subscription.PENDING_AUTHORIZATIONS.has(bob["attempt_id"], "bob")


def test_malformed_mismatch_and_expiry_never_exchange_credentials():
    start = subscription.start_authorization("alice", now=100)
    called = False

    def exchange(**_values):
        nonlocal called
        called = True
        return {}

    with pytest.raises(subscription.AnthropicSubscriptionFlowError, match="malformed"):
        subscription.complete_authorization(
            "alice", start["attempt_id"], "code-only", exchange=exchange, now=101
        )
    with pytest.raises(subscription.AnthropicSubscriptionFlowError, match="expired"):
        subscription.complete_authorization(
            "alice",
            start["attempt_id"],
            f"synthetic-code#{_state(start)}",
            exchange=exchange,
            now=100 + subscription.ANTHROPIC_PENDING_AUTHORIZATION_SECONDS + 1,
        )
    assert called is False


def test_exchange_uses_json_pkce_without_exposing_upstream_body(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(
            200,
            json={
                "access_token": "synthetic-access",
                "refresh_token": "synthetic-refresh",
                "expires_in": 3600,
            },
        )

    monkeypatch.setattr(subscription.httpx, "post", fake_post)
    result = subscription.exchange_authorization_code(
        "synthetic-code", "synthetic-verifier", "synthetic-state"
    )

    assert result["refresh_token"] == "synthetic-refresh"
    assert captured["url"] == "https://claude.ai/v1/oauth/token"
    assert captured["json"]["code"] == "synthetic-code"
    assert captured["json"]["code_verifier"] == "synthetic-verifier"
    assert captured["json"]["state"] == "synthetic-state"


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        (401, "invalid_grant", subscription.AnthropicSubscriptionReauthRequired),
        (403, "invalid_token", subscription.AnthropicSubscriptionReauthRequired),
        (429, "rate_limit_error", subscription.AnthropicSubscriptionRateLimited),
        (502, "upstream_secret_body", subscription.AnthropicSubscriptionError),
    ],
)
def test_oauth_error_classes_are_safe(monkeypatch, status, error, expected):
    def fake_post(*_args, **_kwargs):
        return httpx.Response(
            status,
            json={
                "error": error,
                "error_description": "synthetic-access must never surface",
            },
        )

    monkeypatch.setattr(subscription.httpx, "post", fake_post)
    with pytest.raises(expected) as raised:
        subscription.refresh_oauth_tokens("synthetic-refresh")
    assert "synthetic-access" not in str(raised.value)
    if status == 429:
        assert "quota" in str(raised.value).lower()
        assert "reconnect" not in str(raised.value).lower()


def _auth_db(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'auth.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(
        subscription,
        "_database_handles",
        lambda: (ProviderAuthSession, TestSessionLocal, datetime.utcnow),
    )
    return TestSessionLocal


def test_refresh_is_serialized_at_60_seconds_and_rotation_commits(monkeypatch, tmp_path):
    TestSessionLocal = _auth_db(monkeypatch, tmp_path)
    db = TestSessionLocal()
    db.add(
        ProviderAuthSession(
            id="anth-auth",
            provider=subscription.ANTHROPIC_SUBSCRIPTION_PROVIDER,
            owner="alice",
            base_url=subscription.DEFAULT_ANTHROPIC_SUBSCRIPTION_BASE_URL,
            access_token="synthetic-old-access",
            refresh_token="synthetic-old-refresh",
            expires_at=datetime.utcnow() + timedelta(seconds=30),
            auth_mode=subscription.ANTHROPIC_SUBSCRIPTION_AUTH_MODE,
        )
    )
    db.commit()
    db.close()

    calls = []

    def refresh(refresh_token):
        calls.append(refresh_token)
        return {
            "access_token": "synthetic-new-access",
            "refresh_token": "synthetic-new-refresh",
            "expires_in": 3600,
        }

    monkeypatch.setattr(subscription, "refresh_oauth_tokens", refresh)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(
            pool.map(
                lambda _: subscription.resolve_runtime_credentials(
                    "anth-auth", owner="alice"
                ),
                range(5),
            )
        )

    assert calls == ["synthetic-old-refresh"]
    assert {result["api_key"] for result in results} == {
        "synthetic-new-access"
    }
    db = TestSessionLocal()
    row = db.query(ProviderAuthSession).filter_by(id="anth-auth").one()
    assert row.access_token == "synthetic-new-access"
    assert row.refresh_token == "synthetic-new-refresh"
    assert row.expires_at > datetime.utcnow() + timedelta(minutes=50)
    db.close()


def test_refresh_failure_preserves_recoverable_row_and_owner_isolation(
    monkeypatch, tmp_path
):
    TestSessionLocal = _auth_db(monkeypatch, tmp_path)
    db = TestSessionLocal()
    db.add(
        ProviderAuthSession(
            id="anth-auth-failure",
            provider=subscription.ANTHROPIC_SUBSCRIPTION_PROVIDER,
            owner="alice",
            base_url=subscription.DEFAULT_ANTHROPIC_SUBSCRIPTION_BASE_URL,
            access_token="synthetic-old-access",
            refresh_token="synthetic-old-refresh",
            expires_at=datetime.utcnow() - timedelta(seconds=1),
            auth_mode=subscription.ANTHROPIC_SUBSCRIPTION_AUTH_MODE,
        )
    )
    db.commit()
    db.close()

    def fail(_refresh):
        raise subscription.AnthropicSubscriptionReauthRequired("Reconnect")

    monkeypatch.setattr(subscription, "refresh_oauth_tokens", fail)
    with pytest.raises(subscription.AnthropicSubscriptionAuthNotFound):
        subscription.resolve_runtime_credentials(
            "anth-auth-failure", owner="bob"
        )
    with pytest.raises(subscription.AnthropicSubscriptionReauthRequired):
        subscription.resolve_runtime_credentials(
            "anth-auth-failure", owner="alice"
        )

    db = TestSessionLocal()
    row = db.query(ProviderAuthSession).filter_by(id="anth-auth-failure").one()
    assert row.access_token == "synthetic-old-access"
    assert row.refresh_token == "synthetic-old-refresh"
    db.close()


def test_oauth_headers_and_transforms_do_not_affect_api_key_shape():
    oauth = subscription.anthropic_subscription_headers("synthetic-access")
    assert oauth["Authorization"] == "Bearer synthetic-access"
    assert oauth["anthropic-version"] == "2023-06-01"
    assert "x-api-key" not in oauth
    assert "1m" not in oauth["anthropic-beta"].lower()

    payload = {
        "system": [{"type": "text", "text": "App instructions"}],
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "call-1",
                        "name": "read_file",
                        "input": {},
                    }
                ],
            },
        ],
        "tools": [{"name": "read_file", "input_schema": {"type": "object"}}],
    }
    transformed = subscription.transform_oauth_messages(payload)
    transformed = subscription.transform_oauth_tools(transformed)

    assert transformed["system"][0]["text"] == subscription.CLAUDE_CODE_SYSTEM_IDENTITY
    assert transformed["messages"][0]["content"][0]["text"] == "App instructions"
    assert transformed["messages"][1]["content"][0]["name"] == "mcp_Read_file"
    assert transformed["tools"][0]["name"] == "mcp_Read_file"
    assert subscription.strip_oauth_tool_name("mcp_Read_file") == "read_file"
    assert payload["tools"][0]["name"] == "read_file"
